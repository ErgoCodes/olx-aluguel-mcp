"""Servidor MCP para buscar y analizar alquileres en OLX Brasil."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from . import analysis
from .client import (
    CATEGORY_ID_TO_KEY,
    COMPLEX_CODES,
    FEATURE_CODES,
    OlxClient,
    OlxError,
    build_search_url,
    market_location_for_ad,
    with_page,
)
from .parsers import ParseError, fmt_brl

mcp = FastMCP("olx_aluguel_mcp")
client = OlxClient()

RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}
Fmt = Literal["markdown", "json"]
DEFAULT_LOC = "estado-pr/regiao-de-curitiba-e-paranagua"


# ---------------------------------------------------------------------------
# Lógica compartida
# ---------------------------------------------------------------------------

async def _market_for(ad: dict) -> tuple[dict | None, str | None]:
    """Busca anuncios comparables (misma zona, tipo y nº de habitaciones)."""
    loc = market_location_for_ad(ad)
    if not loc:
        return None, None
    tipo = CATEGORY_ID_TO_KEY.get(ad.get("categoria_id"), "todos")
    rooms = ad.get("habitaciones")
    attempts = []
    if rooms is not None:
        attempts.append(build_search_url(loc, tipo=tipo, habitaciones=[rooms], ordenar="relevancia"))
    attempts.append(build_search_url(loc, tipo=tipo, ordenar="relevancia"))
    for url in attempts:
        try:
            res = await client.fetch_search(url)
        except (OlxError, ParseError):
            continue
        stats = analysis.market_stats(res["anuncios"], exclude_list_id=ad.get("list_id"))
        if stats:
            stats["url_comparacion"] = url
            return stats, url
    return None, None


async def _full_analysis(url_or_id: str, comparar_mercado: bool = True) -> dict:
    ad = await client.fetch_ad(url_or_id)
    tasks = [client.fetch_seller(ad["list_id"])]
    cep = (ad.get("ubicacion") or {}).get("cep")
    tasks.append(client.fetch_cep(cep) if cep else asyncio.sleep(0, result=None))
    seller, cep_info = await asyncio.gather(*tasks)
    market, _ = (await _market_for(ad)) if comparar_mercado else (None, None)

    costs = analysis.extract_costs(ad)
    contacts = analysis.extract_contacts(ad)
    address = analysis.extract_address(ad, cep_info)
    owner = analysis.owner_assessment(ad, seller)
    cmp_ = analysis.price_vs_market(ad, market)
    risk = analysis.fraud_risk(ad, seller, contacts, address, owner, cmp_)
    return {
        "anuncio": {k: v for k, v in ad.items() if k not in ("imagenes", "bloque_precios_olx")},
        "anunciante_perfil": seller,
        "costos": costs,
        "contactos": contacts,
        "direccion": address,
        "trato_con_dueno": owner,
        "mercado": market,
        "precio_vs_mercado": cmp_,
        "riesgo_fraude": risk,
        "preguntas_sugeridas": analysis.questions_to_ask(costs, owner),
        "checklist_seguridad": analysis.CHECKLIST,
    }


def _err(e: Exception) -> str:
    if isinstance(e, (OlxError, ParseError)):
        return f"Error: {e}"
    return f"Error inesperado ({type(e).__name__}): {e}"


def _yn(v) -> str:
    return "sí" if v else "no"


# ---------------------------------------------------------------------------
# Formato Markdown
# ---------------------------------------------------------------------------

def _md_search(res: dict, url: str, analyzed: dict[int, dict]) -> str:
    lines = [
        f"## {res.get('titulo_pagina') or 'Resultados'}",
        f"Total en OLX: **{res.get('total')}** · página {res.get('pagina')} · mostrando {len(res['anuncios'])}",
        f"URL de búsqueda: {url}",
        "",
    ]
    for i, a in enumerate(res["anuncios"], 1):
        who = "Inmobiliaria/corretor" if a["profesional"] else "Particular"
        feats = []
        if a.get("area_m2"):
            feats.append(f"{a['area_m2']} m²")
        if a.get("habitaciones") is not None:
            feats.append(f"{a['habitaciones']} hab.")
        if a.get("banos") is not None:
            feats.append(f"{a['banos']} baño(s)")
        if a.get("garajes"):
            feats.append(f"{a['garajes']} vaga(s)")
        flags = a.get("alertas") or []
        lines.append(f"### {i}. {a['titulo']}")
        lines.append(
            f"- **Alquiler {fmt_brl(a['alquiler'])}** · condominio {fmt_brl(a['condominio'])} · IPTU {fmt_brl(a['iptu'])}"
            f" · **total ≈ {fmt_brl(a['total_estimado'])}/mes**"
            + (f" · {fmt_brl(a['precio_m2'])}/m²" if a.get("precio_m2") else "")
        )
        lines.append(f"- {', '.join(feats) or '—'} · {a.get('ubicacion') or ''} · {who}: {a.get('anunciante') or '—'}")
        lines.append(f"- Publicado: {(a.get('fecha') or '')[:10]} · {a.get('fotos')} fotos · {a['url']}")
        if a.get("caracteristicas"):
            lines.append(f"- Detalles: {', '.join(a['caracteristicas'])}")
        if flags:
            lines.append(f"- ⚠️ {' | '.join(flags)}")
        an = analyzed.get(a["list_id"])
        if an:
            r = an["riesgo_fraude"]
            lines.append(
                f"- **Riesgo de fraude: {r['nivel']} ({r['puntaje']}/100)** · "
                f"{an['trato_con_dueno']['veredicto']}"
            )
            for s in r["senales_de_alerta"][:3]:
                if s["puntos"] > 0:
                    lines.append(f"  - {s['senal']}")
        lines.append("")
    return "\n".join(lines)


def _md_analysis(r: dict, include_description: bool = True) -> str:
    ad, s, c, ct, d, o, risk = (
        r["anuncio"], r["anunciante_perfil"], r["costos"], r["contactos"],
        r["direccion"], r["trato_con_dueno"], r["riesgo_fraude"],
    )
    L = [f"# {ad['titulo']}", ad["url"], ""]
    L.append(f"**Riesgo de fraude: {risk['nivel']} ({risk['puntaje']}/100)** — {risk['aviso']}")
    for x in risk["senales_de_alerta"]:
        if x["puntos"] > 0:
            L.append(f"- 🔴 [{x['gravedad']}] {x['senal']}")
        else:
            L.append(f"- ℹ️ {x['senal']}")
    for g in risk["senales_positivas"]:
        L.append(f"- 🟢 {g}")

    L += ["", "## Costos mensuales"]
    decl = c["declarado_en_olx"]
    L.append(f"| Concepto | Valor |\n|---|---|")
    L.append(f"| Alquiler | {fmt_brl(decl['alquiler'])} |")
    L.append(f"| Condominio | {fmt_brl(decl['condominio'])} |")
    L.append(f"| IPTU | {fmt_brl(decl['iptu'])} |")
    L.append(f"| **Total (alquiler+cond.+IPTU)** | **{fmt_brl(c['total_mensual_base'])}** |")
    if decl.get("total_estimado_olx"):
        L.append(f"| Total estimado por OLX | {fmt_brl(decl['total_estimado_olx'])} |")
    if c["conceptos_en_texto"]:
        L.append("\n**Otros pagos/condiciones mencionados en el texto:**")
        shown: set[str] = set()
        for it in c["conceptos_en_texto"]:
            v = ", ".join(fmt_brl(x) for x in it["valores"]) if it["valores"] else ""
            if it.get("porcentaje"):
                v = (v + " " if v else "") + it["porcentaje"]
            inc = {True: " (incluido)", False: " (NO incluido / aparte)", None: ""}[it["incluido"]]
            meses = f" ({it['meses']} meses)" if it.get("meses") else ""
            quote = it["menciones"][0][:160] if it["menciones"] else ""
            q = f" — “{quote}”" if quote and quote not in shown else ""
            shown.add(quote)
            L.append(f"- **{it['concepto'].replace('_', ' ')}**{meses}{inc}{': ' + v if v else ''}{q}")
    if c["garantias_mencionadas"] or c["sin_fiador_mencionado"]:
        g = ", ".join(x.replace("_", " ") for x in c["garantias_mencionadas"]) or "—"
        L.append(f"- Garantías mencionadas: {g}" + (" · dice 'sin fiador'" if c["sin_fiador_mencionado"] else ""))
    for n in c["notas"]:
        L.append(f"- ⚠️ {n}")

    L += ["", "## ¿Directo con el dueño?", f"**{o['veredicto']}** (probabilidad de trato directo: {o['probabilidad_trato_directo_con_dueno']})"]
    L += [f"- ✔ {x}" for x in o["a_favor"]] + [f"- ✘ {x}" for x in o["en_contra"]]

    L += ["", "## Anunciante"]
    an = ad["anunciante"]
    L.append(f"- Nombre: {an['nombre']} · {'profesional' if an['profesional'] else 'particular'}")
    if s:
        L.append(f"- En OLX desde: {(s.get('cuenta_creada') or '')[:10]} · cuenta nueva: {_yn(s['cuenta_nueva'])}")
        L.append(
            f"- Verificado por OLX → identidad: {_yn(s['identidad_verificada'])} · teléfono: {_yn(s['telefono_verificado'])}"
            f" · e-mail: {_yn(s['email_verificado'])}"
        )
        if s.get("reputacion"):
            L.append(f"- Reputación: {s['reputacion']}")
        if s.get("ubicacion_anunciante"):
            u = s["ubicacion_anunciante"]
            L.append(f"- Ubicación del anunciante: {u.get('neighbourhood', '')} {u.get('city', '')}/{u.get('state', '')}")
        if s.get("ultima_actividad"):
            L.append(f"- Última actividad: {s['ultima_actividad'][:16].replace('T', ' ')} UTC")
        if s.get("tiempo_respuesta_chat"):
            L.append(f"- Responde en el chat en: {s['tiempo_respuesta_chat']}")

    L += ["", "## Contactos"]
    tel = ct["telefono_en_olx"]
    L.append(
        f"- Teléfono en OLX: {'registrado' if tel['registrado'] else 'no informado'}"
        + (f" (empieza por {tel['digitos_visibles']})" if tel.get("digitos_visibles") else "")
        + f" · verificado: {_yn(tel['verificado_por_olx'])} → {tel['como_verlo']}"
    )
    L.append(f"- Chat OLX: {_yn(ct['chat_olx_habilitado'])} · WhatsApp vía OLX: {_yn(ct['whatsapp_olx_habilitado'])}")
    for key, label in [("telefonos_en_texto", "Teléfonos en el texto"), ("numeros_escritos_con_palabras", "Números escritos con palabras"),
                       ("emails_en_texto", "E-mails en el texto"), ("links_en_texto", "Links en el texto"),
                       ("instagram", "Instagram"), ("creci", "CRECI mencionado")]:
        if ct.get(key):
            L.append(f"- {label}: {', '.join(ct[key])}")
    if ct.get("menciona_whatsapp"):
        L.append("- El texto menciona WhatsApp.")

    L += ["", "## Ubicación"]
    L.append(f"- {d['barrio_declarado']}, {d['municipio']}/{d['uf']} · CEP {d['cep'] or '—'}")
    if d.get("direccion_olx"):
        L.append(f"- Dirección que muestra OLX: {d['direccion_olx']}")
    if d.get("calle_segun_cep") and d["calle_segun_cep"].get("calle"):
        cc = d["calle_segun_cep"]
        L.append(f"- Calle del CEP (ViaCEP): {cc['calle']}{' ' + cc['complemento'] if cc.get('complemento') else ''}, {cc.get('barrio') or ''}")
    L.append(f"- Precisión: {d['precision']}")
    if d["direcciones_en_texto"]:
        L.append(f"- Direcciones en el texto: {'; '.join(d['direcciones_en_texto'])}")
    if d["referencias_cercanas"]:
        L.append(f"- Referencias: {'; '.join(d['referencias_cercanas'])}")
    if d["otros_barrios_mencionados"]:
        L.append(f"- ⚠️ Otros barrios mencionados: {', '.join(d['otros_barrios_mencionados'])}")
    if d.get("mapa_aprox"):
        L.append(f"- Mapa aproximado: {d['mapa_aprox']}")

    L += ["", "## Inmueble"]
    L.append(
        f"- {ad.get('tipo_inmueble') or ad.get('categoria')} · {ad.get('area_m2') or '—'} m² · {ad.get('habitaciones')} hab. · "
        f"{ad.get('banos')} baño(s) · {ad.get('garajes') or 0} vaga(s) · {ad.get('fotos')} fotos"
    )
    if ad.get("caracteristicas"):
        L.append(f"- Inmueble: {', '.join(ad['caracteristicas'])}")
    if ad.get("caracteristicas_condominio"):
        L.append(f"- Condominio: {', '.join(ad['caracteristicas_condominio'])}")
    L.append(f"- Publicado: {(ad.get('fecha_publicacion') or '')[:10]}")

    m, pc = r.get("mercado"), r.get("precio_vs_mercado")
    if m:
        L += ["", "## Comparación con la zona"]
        L.append(
            f"- Muestra: {m['muestra']} anuncios · mediana alquiler {fmt_brl(m['mediana_alquiler'])} "
            f"(P25 {fmt_brl(m['p25_alquiler'])} – P75 {fmt_brl(m['p75_alquiler'])}) · mediana total {fmt_brl(m['mediana_total_mensual'])}"
            + (f" · mediana {fmt_brl(m['mediana_precio_m2'])}/m²" if m.get("mediana_precio_m2") else "")
        )
        if pc:
            L.append(f"- Este anuncio: {pc['diferencia_pct']:+d}% vs {pc['base']}")

    if include_description and ad.get("descripcion"):
        L += ["", "## Descripción original", ad["descripcion"]]
    L += ["", "## Preguntas para el anunciante"] + [f"- {q}" for q in r["preguntas_sugeridas"]]
    L += ["", "## Checklist antes de pagar"] + [f"- {q}" for q in r["checklist_seguridad"]]
    if ad.get("link_denuncia"):
        L.append(f"\nSi sospechas fraude, denúncialo en OLX: {ad['link_denuncia']}")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Herramientas
# ---------------------------------------------------------------------------

@mcp.tool(name="olx_buscar_alquileres", annotations={"title": "Buscar alquileres en OLX", **RO})
async def olx_buscar_alquileres(
    ubicacion: Annotated[str, Field(description=(
        "Ruta de ubicación de OLX (lo que va después de '/imoveis/aluguel/' en la URL). "
        "Ej: 'estado-pr/regiao-de-curitiba-e-paranagua' (región), "
        "'estado-pr/regiao-de-curitiba-e-paranagua/boa-vista' (zona de Curitiba), "
        "'estado-pr/regiao-de-curitiba-e-paranagua/boa-vista/taruma' (barrio), 'estado-sp/sao-paulo-e-regiao'."
    ))] = DEFAULT_LOC,
    tipo: Annotated[Literal["todos", "apartamentos", "casas", "habitaciones"], Field(description="Tipo de inmueble.")] = "todos",
    precio_min: Annotated[int | None, Field(ge=0, description="Alquiler mínimo en R$.")] = None,
    precio_max: Annotated[int | None, Field(ge=0, description="Alquiler máximo en R$.")] = None,
    precio_incluye_condominio: Annotated[bool, Field(description="Si true, el filtro de precio se aplica a alquiler+condominio.")] = False,
    habitaciones: Annotated[list[int] | None, Field(description="Nº exacto de habitaciones aceptadas, ej. [1,2]. 5 = 5 o más.")] = None,
    banos: Annotated[list[int] | None, Field(description="Nº de baños aceptados, ej. [1,2].")] = None,
    garajes: Annotated[list[int] | None, Field(description="Nº de vagas de garaje aceptadas, ej. [1].")] = None,
    area_min: Annotated[int | None, Field(ge=0, description="Área mínima en m².")] = None,
    area_max: Annotated[int | None, Field(ge=0, description="Área máxima en m².")] = None,
    anunciante: Annotated[Literal["todos", "particular", "profesional"], Field(description="'particular' ≈ directo con el dueño; 'profesional' = inmobiliarias/corretores.")] = "todos",
    caracteristicas: Annotated[list[str] | None, Field(description="Características del inmueble: " + ", ".join(FEATURE_CODES))] = None,
    condominio: Annotated[list[str] | None, Field(description="Características del condominio: " + ", ".join(COMPLEX_CODES))] = None,
    texto: Annotated[str | None, Field(description="Texto libre a buscar (en portugués), ej. 'mobiliado', 'próximo PUC'.")] = None,
    ordenar: Annotated[Literal["relevancia", "recientes", "menor_precio", "mayor_precio"], Field(description="Orden de resultados.")] = "recientes",
    pagina: Annotated[int, Field(ge=1, le=100, description="Página de resultados (50 por página).")] = 1,
    url: Annotated[str | None, Field(description="Alternativa: URL de búsqueda de OLX ya filtrada (ignora los demás filtros).")] = None,
    limite: Annotated[int, Field(ge=1, le=50, description="Máximo de anuncios a devolver de la página.")] = 20,
    analizar_top: Annotated[int, Field(ge=0, le=10, description="Analiza en profundidad (fraude, anunciante) los primeros N resultados. Más lento: ~3 s por anuncio.")] = 0,
    formato: Annotated[Fmt, Field(description="'markdown' (legible) o 'json' (estructurado).")] = "markdown",
) -> str:
    """Busca alquileres en OLX Brasil con filtros y devuelve precio, condominio, IPTU, total mensual,
    m², R$/m², tipo de anunciante (particular vs inmobiliaria) y alertas rápidas.
    Con analizar_top>0 además calcula el riesgo de fraude de los primeros resultados."""
    try:
        search_url = with_page(url, pagina) if url else build_search_url(
            ubicacion, tipo, precio_min, precio_max, precio_incluye_condominio, habitaciones, banos, garajes,
            area_min, area_max, anunciante, caracteristicas, condominio, texto, ordenar, pagina,
        )
        res = await client.fetch_search(search_url)
        stats = analysis.market_stats(res["anuncios"])
        res["anuncios"] = res["anuncios"][:limite]
        med_m2 = (stats or {}).get("mediana_precio_m2")
        med = (stats or {}).get("mediana_alquiler")
        for a in res["anuncios"]:
            flags = []
            if med_m2 and a.get("precio_m2") and a["precio_m2"] < 0.6 * med_m2:
                flags.append(f"R$/m² {round((a['precio_m2'] / med_m2 - 1) * 100)}% vs mediana de esta búsqueda")
            elif med and a.get("alquiler") and not a.get("area_m2") and a["alquiler"] < 0.5 * med:
                flags.append("alquiler muy por debajo de la mediana de esta búsqueda")
            if a.get("alquiler") and a["alquiler"] > 60000:
                flags.append("precio de venta? (mal categorizado)")
            if a.get("fotos") is not None and a["fotos"] < 4:
                flags.append(f"solo {a['fotos']} fotos")
            a["alertas"] = flags
        analyzed: dict[int, dict] = {}
        for a in res["anuncios"][:analizar_top]:
            try:
                analyzed[a["list_id"]] = await _full_analysis(a["url"], comparar_mercado=False)
                if stats:
                    ad = analyzed[a["list_id"]]
                    cmp_ = analysis.price_vs_market(ad["anuncio"], stats)
                    ad["precio_vs_mercado"] = cmp_
                    ad["riesgo_fraude"] = analysis.fraud_risk(
                        ad["anuncio"], ad["anunciante_perfil"], ad["contactos"], ad["direccion"], ad["trato_con_dueno"], cmp_)
            except Exception as e:  # noqa: BLE001
                a["alertas"].append(f"no se pudo analizar: {e}")
        if formato == "json":
            for a in res["anuncios"]:
                if a["list_id"] in analyzed:
                    an = analyzed[a["list_id"]]
                    a["riesgo_fraude"] = an["riesgo_fraude"]
                    a["trato_con_dueno"] = an["trato_con_dueno"]
            return json.dumps({"url": search_url, "estadisticas_pagina": stats, **res}, ensure_ascii=False, indent=2)
        md = _md_search(res, search_url, analyzed)
        if stats:
            md += (f"\n---\nMediana de esta página: alquiler {fmt_brl(stats['mediana_alquiler'])}"
                   + (f", {fmt_brl(stats['mediana_precio_m2'])}/m²" if stats.get("mediana_precio_m2") else "")
                   + f" (n={stats['muestra']}).")
        if res.get("total") and res["total"] > (res.get("pagina") or 1) * (res.get("tamano_pagina") or 50):
            md += f"\nHay más resultados: usa pagina={(res.get('pagina') or 1) + 1}."
        return md
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool(name="olx_ver_anuncio", annotations={"title": "Ver detalle de un anuncio", **RO})
async def olx_ver_anuncio(
    anuncio: Annotated[str, Field(description="URL del anuncio de OLX o su número (list id), ej. '1538924824'.")],
    formato: Annotated[Fmt, Field(description="'markdown' o 'json'.")] = "markdown",
) -> str:
    """Detalle completo de un anuncio: todos los pagos (alquiler, condominio, IPTU, bruto/líquido, seguros,
    garantías, tasas mencionadas), si es directo con el dueño, contactos que aparecen, dirección/CEP,
    perfil del anunciante y riesgo de fraude. No compara con el mercado (usa olx_analizar_riesgo para eso)."""
    try:
        r = await _full_analysis(anuncio, comparar_mercado=False)
        return json.dumps(r, ensure_ascii=False, indent=2) if formato == "json" else _md_analysis(r)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool(name="olx_analizar_riesgo", annotations={"title": "Analizar riesgo de fraude", **RO})
async def olx_analizar_riesgo(
    anuncio: Annotated[str, Field(description="URL del anuncio de OLX o su número (list id).")],
    comparar_mercado: Annotated[bool, Field(description="Compara el precio con anuncios similares de la misma zona (1-2 consultas extra).")] = True,
    formato: Annotated[Fmt, Field(description="'markdown' o 'json'.")] = "markdown",
) -> str:
    """Evalúa el riesgo de estafa ('golpe do aluguel') de un anuncio: precio vs. mercado de la zona,
    antigüedad y verificaciones de la cuenta, frases típicas de estafa (pago antes de visitar, dueño en
    el exterior, llaves por correo...), contactos fuera de OLX, fotos, coherencia de ubicación.
    Devuelve puntaje 0-100, señales, preguntas para el anunciante y checklist de seguridad."""
    try:
        r = await _full_analysis(anuncio, comparar_mercado=comparar_mercado)
        return json.dumps(r, ensure_ascii=False, indent=2) if formato == "json" else _md_analysis(r)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool(name="olx_comparar_anuncios", annotations={"title": "Comparar anuncios", **RO})
async def olx_comparar_anuncios(
    anuncios: Annotated[list[str], Field(min_length=2, max_length=10, description="Lista de 2 a 10 URLs o números de anuncios.")],
    formato: Annotated[Fmt, Field(description="'markdown' o 'json'.")] = "markdown",
) -> str:
    """Compara varios anuncios lado a lado: costo mensual total, m², R$/m², pagos extra, garantías,
    tipo de anunciante y riesgo de fraude."""
    rows, errors = [], []
    for a in anuncios:
        try:
            r = await _full_analysis(a, comparar_mercado=False)
            ad, c = r["anuncio"], r["costos"]
            extras = [x["concepto"].replace("_", " ") for x in c["conceptos_en_texto"]
                      if x["concepto"] not in ("condominio", "iptu", "aluguel_liquido")]
            rows.append({
                "titulo": ad["titulo"], "url": ad["url"], "barrio": ad["ubicacion"]["barrio"],
                "alquiler": ad["alquiler"], "condominio": ad["condominio"], "iptu": ad["iptu"],
                "total": c["total_mensual_base"], "area_m2": ad["area_m2"],
                "precio_m2": round(ad["alquiler"] / ad["area_m2"], 2) if ad.get("alquiler") and ad.get("area_m2") else None,
                "habitaciones": ad["habitaciones"], "garajes": ad["garajes"],
                "anunciante": r["trato_con_dueno"]["veredicto"], "riesgo": f"{r['riesgo_fraude']['nivel']} ({r['riesgo_fraude']['puntaje']})",
                "extras_mencionados": extras, "garantias": c["garantias_mencionadas"], "notas": c["notas"],
            })
        except Exception as e:  # noqa: BLE001
            errors.append(f"{a}: {_err(e)}")
    if formato == "json":
        return json.dumps({"comparacion": rows, "errores": errors}, ensure_ascii=False, indent=2)
    rows.sort(key=lambda x: x["total"] or 1e12)
    L = ["| # | Anuncio | Barrio | Alquiler | Cond. | IPTU | **Total** | m² | R$/m² | Hab. | Anunciante | Riesgo |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, x in enumerate(rows, 1):
        L.append(
            f"| {i} | [{x['titulo'][:45]}]({x['url']}) | {x['barrio']} | {fmt_brl(x['alquiler'])} | {fmt_brl(x['condominio'])} | "
            f"{fmt_brl(x['iptu'])} | **{fmt_brl(x['total'])}** | {x['area_m2'] or '—'} | {fmt_brl(x['precio_m2'])} | "
            f"{x['habitaciones'] if x['habitaciones'] is not None else '—'} | {x['anunciante']} | {x['riesgo']} |"
        )
    for i, x in enumerate(rows, 1):
        det = []
        if x["extras_mencionados"]:
            det.append("pagos/condiciones mencionados: " + ", ".join(x["extras_mencionados"]))
        if x["notas"]:
            det.append("; ".join(x["notas"]))
        if det:
            L.append(f"\n**{i}.** " + " · ".join(det))
    if errors:
        L.append("\nErrores:\n" + "\n".join(f"- {e}" for e in errors))
    return "\n".join(L)


@mcp.tool(name="olx_precios_mercado", annotations={"title": "Precios de referencia de una zona", **RO})
async def olx_precios_mercado(
    ubicacion: Annotated[str, Field(description="Ruta de ubicación de OLX, ej. 'estado-pr/regiao-de-curitiba-e-paranagua/boa-vista/taruma'.")] = DEFAULT_LOC,
    tipo: Annotated[Literal["todos", "apartamentos", "casas", "habitaciones"], Field(description="Tipo de inmueble.")] = "apartamentos",
    habitaciones: Annotated[list[int] | None, Field(description="Nº de habitaciones, ej. [1] o [2,3].")] = None,
    paginas: Annotated[int, Field(ge=1, le=3, description="Páginas a muestrear (50 anuncios c/u).")] = 1,
) -> str:
    """Precio de referencia de alquiler en una zona: mediana, rango P25–P75, total mensual con
    condominio+IPTU y R$/m². Útil para saber si un anuncio está caro o sospechosamente barato."""
    try:
        items = []
        base = build_search_url(ubicacion, tipo=tipo, habitaciones=habitaciones, ordenar="relevancia")
        total = None
        for p in range(1, paginas + 1):
            res = await client.fetch_search(with_page(base, p))
            total = res.get("total")
            items.extend(res["anuncios"])
            if len(res["anuncios"]) < (res.get("tamano_pagina") or 50):
                break
        st = analysis.market_stats(items)
        if not st:
            return f"No hay suficientes anuncios para calcular estadísticas ({len(items)} encontrados). URL: {base}"
        part = sum(1 for i in items if not i["profesional"])
        return (
            f"## Precios de alquiler — {ubicacion} ({tipo}{', ' + '/'.join(map(str, habitaciones)) + ' hab.' if habitaciones else ''})\n"
            f"- Anuncios en OLX: {total} · muestra analizada: {st['muestra']} ({part} de particulares)\n"
            f"- Mediana alquiler: **{fmt_brl(st['mediana_alquiler'])}** (P25 {fmt_brl(st['p25_alquiler'])} – P75 {fmt_brl(st['p75_alquiler'])})\n"
            f"- Mediana total (alquiler+cond.+IPTU): **{fmt_brl(st['mediana_total_mensual'])}**\n"
            + (f"- Mediana R$/m²: **{fmt_brl(st['mediana_precio_m2'])}** (n={st['muestra_m2']})\n" if st.get("mediana_precio_m2") else "")
            + f"- Fuente: {base}\n"
            "Nota: son precios pedidos (no de cierre) y OLX a veces clasifica mal ventas o diarias; se excluyen valores < R$ 250 y > R$ 60.000."
        )
    except Exception as e:  # noqa: BLE001
        return _err(e)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
