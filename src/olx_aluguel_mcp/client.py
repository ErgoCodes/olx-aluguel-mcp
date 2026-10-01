"""Cliente HTTP para OLX: construcción de URLs, límite de frecuencia y caché."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from urllib.parse import urlencode, urlparse

from . import parsers

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,es;q=0.8,en;q=0.7",
}

MIN_INTERVAL_S = 1.5      # pausa mínima entre peticiones a OLX (sé amable)
CACHE_TTL_S = 600         # 10 minutos
TIMEOUT_S = 25
FORCE_BROWSER = os.environ.get("OLX_USE_BROWSER", "").lower() in ("1", "true", "yes")

CATEGORY_PATHS = {
    "todos": "",
    "apartamentos": "apartamentos",
    "casas": "casas",
    "habitaciones": "aluguel-de-quartos",
}
CATEGORY_ID_TO_KEY = {1020: "apartamentos", 1040: "casas", 1060: "habitaciones"}

SORT_PARAMS = {
    "relevancia": {},
    "recientes": {"sf": "1"},
    "menor_precio": {"sp": "1"},
    "mayor_precio": {"sp": "5"},
}
FEATURE_CODES = {  # rfs
    "academia": 100, "aquecimento": 101, "ar_condicionado": 102, "area_servico": 103,
    "armarios_cozinha": 104, "armarios_quarto": 105, "banheiro_no_quarto": 106,
    "churrasqueira": 107, "internet": 108, "mobiliado": 109, "piscina": 110, "porteiro_24h": 111,
}
COMPLEX_CODES = {  # rcf
    "academia": 200, "area_murada": 201, "condominio_fechado": 202, "elevador": 203,
    "aceita_pet": 204, "piscina": 205, "portao_eletronico": 206, "portaria": 207,
    "salao_festas": 208, "seguranca_24h": 209,
}


class OlxError(Exception):
    pass


class OlxClient:
    def __init__(self) -> None:
        self._last = 0.0
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[float, str]] = {}
        self._session = None
        self._backend = None

    async def _get_session(self):
        if self._session is not None:
            return self._session
        try:  # curl_cffi imita la huella TLS de Chrome -> menos bloqueos
            from curl_cffi.requests import AsyncSession  # type: ignore

            self._session = AsyncSession(impersonate="chrome", timeout=TIMEOUT_S)
            self._backend = "curl_cffi"
        except Exception:  # pragma: no cover - fallback
            import httpx

            self._session = httpx.AsyncClient(
                headers=BASE_HEADERS, follow_redirects=True, timeout=TIMEOUT_S, http2=False
            )
            self._backend = "httpx"
        return self._session

    async def _throttle(self) -> None:
        async with self._lock:
            wait = MIN_INTERVAL_S - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

    async def get_text(self, url: str, headers: dict | None = None, use_cache: bool = True) -> str:
        now = time.time()
        if use_cache and url in self._cache and now - self._cache[url][0] < CACHE_TTL_S:
            return self._cache[url][1]
        is_olx_html = "olx.com.br" in url and "adview-bff" not in url
        if FORCE_BROWSER and is_olx_html:
            text = await self._browser_get(url)
            self._cache[url] = (now, text)
            return text
        session = await self._get_session()
        await self._throttle()
        if self._backend == "curl_cffi":
            # curl_cffi ya envía el User-Agent coherente con la huella de Chrome
            hdrs = {k: v for k, v in BASE_HEADERS.items() if k != "User-Agent"}
        else:
            hdrs = dict(BASE_HEADERS)
        if headers:
            hdrs.update(headers)
        try:
            if self._backend == "curl_cffi":
                r = await session.get(url, headers=hdrs, allow_redirects=True)
            else:
                r = await session.get(url, headers=hdrs)
        except Exception as e:
            raise OlxError(f"Error de red al acceder a {urlparse(url).netloc} ({type(e).__name__}: {e}). Revisa tu conexión.") from e
        status = r.status_code
        text = r.text
        challenged = status in (403, 503) and _looks_like_challenge(text)
        if (challenged or (status == 200 and _looks_like_challenge(text) and "initial-data" not in text and "__next_f" not in text)) and is_olx_html:
            # Cloudflare pidió verificación de navegador -> intentar con navegador real (si está instalado)
            text = await self._browser_get(url)
            self._cache[url] = (now, text)
            return text
        if status in (404, 410):
            raise OlxError("El anuncio o la página no existe (404). Puede que el anuncio haya sido eliminado.")
        if status in (403, 429):
            raise OlxError(
                f"OLX rechazó la petición (HTTP {status}). Probablemente por demasiadas consultas seguidas; "
                "espera unos minutos y vuelve a intentar con menos páginas/análisis."
            )
        if status >= 400:
            raise OlxError(f"HTTP {status} al acceder a {url}.")
        self._cache[url] = (now, text)
        return text

    async def _browser_get(self, url: str) -> str:
        """Plan B: descarga la página con Chromium headless (requiere `pip install playwright`
        y `playwright install chromium`)."""
        try:
            from playwright.async_api import async_playwright  # type: ignore
        except ImportError as e:
            raise OlxError(
                "OLX/Cloudflare pidió verificación de navegador y Playwright no está instalado. "
                "Instálalo con: pip install playwright && playwright install chromium  (y reinicia Claude Desktop)."
            ) from e
        await self._throttle()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page(locale="pt-BR")
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_S * 1000)
                for _ in range(10):  # esperar si hay desafío de Cloudflare
                    html_ = await page.content()
                    if not _looks_like_challenge(html_):
                        break
                    await page.wait_for_timeout(1500)
                if resp is not None and resp.status in (404, 410):
                    raise OlxError("El anuncio o la página no existe (404).")
                html_ = await page.content()
            finally:
                await browser.close()
        if _looks_like_challenge(html_):
            raise OlxError("OLX sigue mostrando una verificación anti-bot. Abre olx.com.br en tu navegador y vuelve a intentar más tarde.")
        return html_

    # ------------------------------------------------------------------
    async def fetch_ad(self, url_or_id: str) -> dict:
        url = ad_url(url_or_id)
        page = await self.get_text(url)
        return parsers.parse_ad_page(page)

    async def fetch_search(self, url: str) -> dict:
        page = await self.get_text(url)
        return parsers.parse_search_page(page)

    async def fetch_seller(self, list_id: int | str) -> dict | None:
        """Perfil público del anunciante (el mismo que muestra la página del anuncio)."""
        url = f"https://adview-bff.olx.com.br/api/v1/seller/{int(list_id)}"
        try:
            txt = await self.get_text(
                url,
                headers={
                    "Accept": "application/json",
                    "Origin": "https://www.olx.com.br",
                    "Referer": "https://www.olx.com.br/",
                },
            )
            data = json.loads(txt)
        except Exception:
            return None
        return parse_seller(data)

    async def fetch_cep(self, cep: str) -> dict | None:
        """Calle/barrio del CEP vía ViaCEP (API pública brasileña)."""
        cep = re.sub(r"\D", "", cep or "")
        if len(cep) != 8:
            return None
        try:
            txt = await self.get_text(f"https://viacep.com.br/ws/{cep}/json/", headers={"Accept": "application/json"})
            data = json.loads(txt)
        except Exception:
            return None
        if data.get("erro"):
            return None
        return {
            "calle": data.get("logradouro") or None,
            "complemento": data.get("complemento") or None,
            "barrio": data.get("bairro") or None,
            "ciudad": data.get("localidade") or None,
            "uf": data.get("uf") or None,
        }

    async def aclose(self) -> None:
        if self._session is not None:
            try:
                if self._backend == "curl_cffi":
                    await self._session.close()
                else:
                    await self._session.aclose()
            except Exception:
                pass


def _looks_like_challenge(text: str) -> bool:
    head = text[:20000]
    return ("cf-chl" in head or "challenge-platform" in head or "Just a moment..." in head
            or "Attention Required! | Cloudflare" in head)


def parse_seller(d: dict) -> dict:
    """Normaliza el perfil público. El campo de teléfono (ofuscado) se descarta a propósito."""
    fm = d.get("facematch") or {}
    last = d.get("lastActivity") or {}
    locz = d.get("locationDataFromZipCode") or {}
    score = d.get("score") or {}
    return {
        "apodo": d.get("nickname"),
        "cuenta_creada": d.get("creationDate"),
        "cuenta_nueva": bool(d.get("isNewAccount")),
        "es_profesional": bool(d.get("isPro")),
        "identidad_verificada": bool(fm.get("profileVerified")),
        "telefono_verificado": bool(d.get("phoneVerified")),
        "email_verificado": bool(d.get("emailVerified")),
        "facebook_verificado": bool(d.get("facebookVerified")),
        "creci": d.get("creci"),
        "reputacion": score.get("description"),
        "tiempo_respuesta_chat": d.get("chatTimeResponse"),
        "ultima_actividad": last.get("timestamp"),
        "ubicacion_anunciante": {k: v for k, v in locz.items() if v} or None,
        "perfil_url": f"https://www.olx.com.br/perfil/{d['slug']}" if d.get("slug") else None,
        "cnpj_verificado": (d.get("configs") or {}).get("cnpjVerified"),
    }


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

def ad_url(url_or_id: str) -> str:
    s = str(url_or_id).strip()
    if re.fullmatch(r"\d{6,}", s):
        return f"https://www.olx.com.br/vi/{s}"
    parsed = urlparse(s if "://" in s else "https://" + s)
    if not parsed.netloc.endswith("olx.com.br"):
        raise OlxError("La URL no es de olx.com.br. Pasa la URL completa del anuncio o su número (list id).")
    # quitar parámetros de tracking
    return f"https://{parsed.netloc}{parsed.path}"


def list_id_from_url(url: str) -> int | None:
    m = re.search(r"-(\d{6,})(?:[/?#]|$)", url) or re.search(r"/vi/(\d{6,})", url)
    return int(m.group(1)) if m else None


def build_search_url(
    ubicacion: str = "estado-pr/regiao-de-curitiba-e-paranagua",
    tipo: str = "todos",
    precio_min: int | None = None,
    precio_max: int | None = None,
    precio_incluye_condominio: bool = False,
    habitaciones: list[int] | None = None,
    banos: list[int] | None = None,
    garajes: list[int] | None = None,
    area_min: int | None = None,
    area_max: int | None = None,
    anunciante: str = "todos",
    caracteristicas: list[str] | None = None,
    condominio: list[str] | None = None,
    texto: str | None = None,
    ordenar: str = "recientes",
    pagina: int = 1,
) -> str:
    loc = ubicacion.strip().strip("/")
    loc = re.sub(r"^https?://[^/]+/", "", loc)
    loc = re.sub(r"^imoveis/aluguel/", "", loc)
    cat = CATEGORY_PATHS.get(tipo, "")
    path = "/imoveis/aluguel/" + (cat + "/" if cat else "") + loc
    params: list[tuple[str, str]] = []
    if precio_min is not None:
        params.append(("refps" if precio_incluye_condominio else "ps", str(precio_min)))
    if precio_max is not None:
        params.append(("refpe" if precio_incluye_condominio else "pe", str(precio_max)))
    for n in habitaciones or []:
        params.append(("ros", str(min(n, 5))))
    for n in banos or []:
        params.append(("bas", str(min(n, 5))))
    for n in garajes or []:
        params.append(("gsp", str(min(n, 5))))
    if area_min is not None:
        params.append(("ss", str(area_min)))
    if area_max is not None:
        params.append(("se", str(area_max)))
    if anunciante == "particular":
        params.append(("f", "p"))
    elif anunciante == "profesional":
        params.append(("f", "c"))
    for c in caracteristicas or []:
        if c in FEATURE_CODES:
            params.append(("rfs", str(FEATURE_CODES[c])))
    for c in condominio or []:
        if c in COMPLEX_CODES:
            params.append(("rcf", str(COMPLEX_CODES[c])))
    if texto:
        params.append(("q", texto))
    params.extend(SORT_PARAMS.get(ordenar, {}).items())
    if pagina and pagina > 1:
        params.append(("o", str(pagina)))
    qs = ("?" + urlencode(params)) if params else ""
    return "https://www.olx.com.br" + path + qs


def with_page(url: str, page: int) -> str:
    url = re.sub(r"([?&])o=\d+&?", r"\1", url).rstrip("?&")
    if page <= 1:
        return url
    return url + ("&" if "?" in url else "?") + f"o={page}"


def market_location_for_ad(ad: dict) -> str | None:
    """Deriva 'estado-xx/<region>/<zona>' a partir del anuncio para comparar precios."""
    url = ad.get("url") or ""
    p = urlparse(url)
    sub = p.netloc.split(".")[0]
    parts = [x for x in p.path.split("/") if x]
    if len(sub) != 2 or not parts:
        return None
    region = parts[0]
    loc = f"estado-{sub}/{region}"
    zone = (ad.get("ubicacion") or {}).get("zona_slug")
    if zone:
        loc += f"/{zone}"
    return loc
