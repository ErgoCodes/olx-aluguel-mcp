"""Extracción de datos de las páginas públicas de OLX Brasil.

OLX incrusta los datos en el HTML:
- Página de anuncio: <script id="initial-data" data-json="{...}"> (JSON con entidades HTML).
- Página de búsqueda (Next.js App Router): fragmentos `self.__next_f.push([1,"..."])`
  que, concatenados, contienen un objeto `{"ads":[...], "totalOfAds":..., ...}`.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

_INITIAL_DATA_RE = re.compile(
    r'<script[^>]*\bid="initial-data"[^>]*\bdata-json="([^"]*)"', re.S
)
_NEXT_F_RE = re.compile(r"self\.__next_f\.push\((\[.*?\])\)\s*</script>", re.S)
_LD_JSON_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)


class ParseError(Exception):
    """La página no tiene el formato esperado (OLX cambió el HTML o hubo bloqueo)."""


# ---------------------------------------------------------------------------
# Helpers numéricos / texto
# ---------------------------------------------------------------------------

def parse_brl(value: Any) -> float | None:
    """'R$ 1.850' -> 1850.0 ; 'R$ 2.312,50' -> 2312.5 ; None/'' -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value)
    m = re.search(r"\d[\d.\s]*(?:,\d{1,2})?", s)
    if not m:
        return None
    num = m.group(0).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    """'35m²' -> 35 ; '5 ou mais' -> 5 ; '2' -> 2."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    m = re.search(r"\d+", str(value).replace(".", ""))
    return int(m.group(0)) if m else None


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    t = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def normalize(text: str | None) -> str:
    """Minúsculas sin acentos (para comparar/buscar palabras clave)."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize(text)).strip("-")


def fmt_brl(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if s.endswith(",00"):
        s = s[:-3]
    return f"R$ {s}"


def ts_to_iso(ts: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _props_to_dict(properties: list[dict] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in properties or []:
        name = p.get("name")
        if name and name not in out:
            out[name] = p.get("value")
    return out


# ---------------------------------------------------------------------------
# Página de anuncio
# ---------------------------------------------------------------------------

def extract_initial_data(page_html: str) -> dict:
    m = _INITIAL_DATA_RE.search(page_html)
    if not m:
        raise ParseError(
            "No se encontró 'initial-data' en la página del anuncio. "
            "Puede que el anuncio haya sido eliminado, que la URL no sea de un anuncio "
            "o que OLX haya bloqueado la petición."
        )
    try:
        return json.loads(html.unescape(m.group(1)))
    except json.JSONDecodeError as e:
        raise ParseError(f"JSON de 'initial-data' inválido: {e}") from e


def extract_ld_json(page_html: str) -> list[dict]:
    out = []
    for block in _LD_JSON_RE.findall(page_html):
        try:
            out.append(json.loads(block))
        except json.JSONDecodeError:
            continue
    return out


def parse_ad_page(page_html: str) -> dict:
    """Devuelve un dict normalizado con los datos del anuncio."""
    data = extract_initial_data(page_html)
    ad = data.get("ad") or {}
    if not ad.get("listId"):
        raise ParseError("La página no contiene un anuncio (sin listId).")

    props = _props_to_dict(ad.get("properties"))
    loc = ad.get("location") or {}
    user = ad.get("user") or {}
    configs = user.get("configs") or {}
    phone = ad.get("phone") or {}

    # Costos que OLX muestra en el bloque de precio
    price_info = {}
    for item in ad.get("realEstatePriceInfo") or []:
        key = item.get("name")
        price_info[key] = {
            "label": item.get("label"),
            "valor": parse_brl(item.get("value")),
            "periodo": item.get("period"),
            "es_total": bool(item.get("isTotalPrice")),
            "nota": item.get("tooltip"),
        }

    rent = parse_brl(ad.get("priceValue") or ad.get("price"))
    condo = parse_brl(props.get("condominio"))
    iptu = parse_brl(props.get("iptu"))
    total_olx = (price_info.get("estimated_monthly_cost") or {}).get("valor")

    description = strip_html(ad.get("description") or ad.get("body"))

    return {
        "list_id": ad.get("listId"),
        "ad_id": ad.get("adId"),
        "titulo": (ad.get("subject") or "").strip(),
        "url": ad.get("friendlyUrl") or ad.get("canonicalUrl"),
        "descripcion": description,
        "categoria": ad.get("categoryName"),
        "categoria_id": ad.get("category"),
        "tipo_inmueble": props.get("real_estate_type"),
        "subtipo": props.get("re_types"),
        "precio_label": ad.get("priceLabel"),
        "alquiler": rent,
        "precio_anterior": parse_brl(ad.get("oldPrice")),
        "condominio": condo,
        "iptu": iptu,
        "total_estimado_olx": total_olx,
        "bloque_precios_olx": price_info,
        "area_m2": parse_int(props.get("size")),
        "habitaciones": parse_int(props.get("rooms")),
        "banos": parse_int(props.get("bathrooms")),
        "garajes": parse_int(props.get("garage_spaces")),
        "caracteristicas": _split_list(props.get("re_features")),
        "caracteristicas_condominio": _split_list(props.get("re_complex_features")),
        "fecha_publicacion": ad.get("listTime") or ts_to_iso(ad.get("origListTime")),
        "fotos": len(ad.get("images") or []),
        "imagenes": [i.get("original") for i in (ad.get("images") or [])][:30],
        "videos": len(ad.get("videos") or []),
        "ubicacion": {
            "direccion_olx": loc.get("address"),
            "barrio": loc.get("neighbourhood"),
            "municipio": loc.get("municipality"),
            "uf": loc.get("uf"),
            "cep": loc.get("zipcode"),
            "zona_slug": loc.get("zone"),
            "region": loc.get("region"),
            "lat": loc.get("mapLati"),
            "lon": loc.get("mapLong"),
            "ddd": loc.get("ddd"),
            "direccion_completa_publica": bool(configs.get("showFullAddress")),
        },
        "anunciante": {
            "nombre": user.get("name"),
            "public_account_id": user.get("publicAccountId"),
            "profesional": bool(ad.get("professionalAd")),
            "cuenta_pro": bool(configs.get("proAccount")),
            "plan_activo": (configs.get("activePlan") or "").strip('"') or None,
            "whatsapp_habilitado": bool(configs.get("whatsapp"))
            or bool((user.get("whatsapp") or {}).get("enabled")),
            "chat_habilitado": bool(ad.get("chatEnabled")),
        },
        "telefono": {
            "tiene_telefono": bool(phone.get("phoneExist")),
            "oculto": bool(phone.get("phoneHidden")),
            "verificado": bool(phone.get("phoneVerified")),
            "parcial": phone.get("maskedPhone") or None,
        },
        "zap_listing_id": ad.get("zapListingId"),
        "destacado": bool(ad.get("isFeatured")),
        "link_denuncia": ad.get("denounceLink"),
    }


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in str(value).split(",") if v.strip()]


# ---------------------------------------------------------------------------
# Página de búsqueda
# ---------------------------------------------------------------------------

def _rsc_payload(page_html: str) -> str:
    chunks = []
    for raw in _NEXT_F_RE.findall(page_html):
        try:
            arr = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(arr, list) and len(arr) >= 2 and arr[0] == 1 and isinstance(arr[1], str):
            chunks.append(arr[1])
    return "".join(chunks)


def extract_search_data(page_html: str) -> dict:
    payload = _rsc_payload(page_html)
    m = re.search(r'\{"ads":\s*\[', payload)
    idx = m.start() if m else -1
    if idx < 0:
        raise ParseError(
            "No se encontró la lista de anuncios en la página de búsqueda. "
            "Verifica que la URL sea un listado de OLX o que OLX no haya bloqueado la petición."
        )
    try:
        obj, _ = json.JSONDecoder().raw_decode(payload, idx)
    except json.JSONDecodeError as e:
        raise ParseError(f"No se pudo decodificar el listado: {e}") from e
    return obj


def parse_search_page(page_html: str) -> dict:
    obj = extract_search_data(page_html)
    items = []
    for a in obj.get("ads") or []:
        if not a.get("listId"):
            continue  # espacios publicitarios
        items.append(parse_search_item(a))
    return {
        "total": obj.get("totalOfAds"),
        "pagina": obj.get("pageIndex"),
        "tamano_pagina": obj.get("pageSize"),
        "titulo_pagina": obj.get("pageTitle"),
        "anuncios": items,
    }


def parse_search_item(a: dict) -> dict:
    props = _props_to_dict(a.get("properties"))
    locd = a.get("locationDetails") or {}
    rent = parse_brl(a.get("priceValue") or a.get("price"))
    condo = parse_brl(props.get("condominio"))
    iptu = parse_brl(props.get("iptu"))
    area = parse_int(props.get("size"))
    total = None
    if rent is not None:
        total = rent + (condo or 0) + (iptu or 0)
    return {
        "list_id": a.get("listId"),
        "titulo": (a.get("subject") or "").strip(),
        "url": a.get("url"),
        "alquiler": rent,
        "precio_anterior": parse_brl(a.get("oldPrice")),
        "condominio": condo,
        "iptu": iptu,
        "total_estimado": total,
        "area_m2": area,
        "precio_m2": round(rent / area, 2) if rent and area else None,
        "habitaciones": parse_int(props.get("rooms")),
        "banos": parse_int(props.get("bathrooms")),
        "garajes": parse_int(props.get("garage_spaces")),
        "tipo_inmueble": props.get("real_estate_type"),
        "categoria": a.get("categoryName") or a.get("category"),
        "caracteristicas": _split_list(props.get("re_features")),
        "caracteristicas_condominio": _split_list(props.get("re_complex_features")),
        "barrio": locd.get("neighbourhood"),
        "municipio": locd.get("municipality"),
        "uf": locd.get("uf"),
        "ubicacion": a.get("location"),
        "profesional": bool(a.get("professionalAd")),
        "anunciante": (a.get("olxPay") or {}).get("transactionalSellerName"),
        "fecha": ts_to_iso(a.get("date")),
        "fotos": a.get("imageCount") if a.get("imageCount") is not None else len(a.get("images") or []),
        "chat_habilitado": bool(a.get("isChatEnabled")),
        "destacado": bool(a.get("isFeatured")),
    }
