"""Análisis de anuncios de alquiler: costos, contactos, dirección, anunciante y riesgo de fraude.

Todo es heurístico: sirve para priorizar y hacer las preguntas correctas, no reemplaza
visitar el inmueble ni verificar documentos.
"""

from __future__ import annotations

import re
import statistics
from datetime import datetime, timezone

from .parsers import normalize

PCT_RE = re.compile(r"(\d+(?:,\d+)?)\s*%")
MONEY_RE = re.compile(r"r\$\s*([\d.]+(?:,\d{1,2})?)|(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d{3,6},\d{2})(?![\d%])|(?<![\d.,])(\d{1,3}(?:\.\d{3})*|\d{3,6})\s*reais", re.I)

# ---------------------------------------------------------------------------
# 1) Costos y condiciones de pago
# ---------------------------------------------------------------------------

COST_CONCEPTS: list[tuple[str, str]] = [
    # (clave, regex sobre texto normalizado)
    ("aluguel_bruto", r"aluguel bruto|valor bruto"),
    ("aluguel_liquido", r"aluguel liquido|valor liquido"),
    ("bonificacao_pontualidade", r"bonifica|desconto (?:de |por |para )?pontualidade|pagamento em dia|pontualidade"),
    ("condominio", r"condominio|\bcond\.?\b"),
    ("iptu", r"\biptu\b"),
    ("seguro_incendio", r"seguro (?:contra )?incendio|seguro residencial"),
    ("seguro_fianca", r"seguro[ -]fianca|fianca locaticia"),
    ("titulo_capitalizacao", r"titulo de capitaliza|capitalizacao"),
    ("reserva_sinal", r"\bsinal\b|para reservar|taxa de reserva|deposito (?:via |por )?pix"),
    ("caucao_deposito", r"caucao|deposito (?:de |como )?(?:garantia|caucao)|deposito calcao|\b\d\s*(?:meses|alugueis) de (?:caucao|deposito)"),
    ("fiador", r"\bfiador"),
    ("taxa_administracao", r"taxa de administra"),
    ("taxa_contrato_cadastro", r"taxa de (?:contrato|cadastro|intermedia|vistoria|elaboracao)|taxa de locacao"),
    ("corretagem", r"corretagem|comissao"),
    ("fundo_conservacao", r"fundo de conserva|\bfci\b"),
    ("despesas_bancarias", r"despesas? bancaria|tarifa bancaria|taxa (?:de |do )?boleto"),
    ("agua", r"\bagua\b"),
    ("luz", r"\bluz\b|energia (?:eletrica)?|\bcopel\b"),
    ("gas", r"\bgas\b"),
    ("internet", r"\binternet\b|wi-?fi"),
    ("taxa_lixo", r"taxa (?:de )?lixo"),
]

INCLUDED_RE = re.compile(r"inclus[oa]s?|incluid[oa]s?|incluso|ja incluso|tudo incluso|incluindo|com (?:agua|luz|internet)")
NOT_INCLUDED_RE = re.compile(r"nao (?:esta |estao )?inclus|nao incluid|a parte|por conta do (?:locatario|inquilino)|\+ taxas|mais taxas|pago (?:a parte|separad)")
PCT_KEYS = {"fundo_conservacao", "taxa_administracao", "corretagem", "bonificacao_pontualidade", "seguro_incendio", "taxa_contrato_cadastro"}
EXTRA_MONTHLY = {"seguro_incendio": "seguro incendio", "fundo_conservacao": "fondo de conservación (FCI)", "despesas_bancarias": "gastos bancarios/boleto", "seguro_fianca": "seguro fianza", "taxa_lixo": "tasa de basura"}
MONTHLY_SMALL = {"condominio", "iptu", "seguro_incendio", "despesas_bancarias", "agua", "luz", "gas", "internet", "taxa_lixo", "fundo_conservacao"}
RENT_KEYS = {"aluguel_bruto", "aluguel_liquido", "bonificacao_pontualidade"}
GUARANTEE_CONCEPTS = {"seguro_fianca", "titulo_capitalizacao", "caucao_deposito", "fiador"}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[\n;]|(?<=[a-z0-9])\.\s+(?=[A-ZÀ-Ú])", text)
    return [p.strip() for p in parts if p and p.strip()]


def extract_costs(ad: dict) -> dict:
    """Combina lo que OLX declara (campos) con lo que el texto menciona."""
    desc = ad.get("descripcion") or ""
    items: dict[str, dict] = {}

    for sent in _sentences(desc):
        n = normalize(sent)
        for key, rx in COST_CONCEPTS:
            if not re.search(rx, n):
                continue
            entry = items.setdefault(key, {"concepto": key, "valores": [], "incluido": None, "menciones": []})
            vals = [float((a or b or c).replace(".", "").replace(",", ".")) for a, b, c in MONEY_RE.findall(sent)]
            rent_now = ad.get("alquiler") or 0
            if key in MONTHLY_SMALL and rent_now:
                # "R$ 3.200 com condomínio incluso": ese valor es el alquiler, no el condominio
                vals = [v for v in vals if v < 0.9 * rent_now]
            if key == "caucao_deposito" and rent_now and vals and "meses" not in entry:
                ratio = max(vals) / rent_now
                if abs(ratio - round(ratio)) < 0.05 and 1 <= round(ratio) <= 6:
                    entry["meses"] = round(ratio)
            if vals and _only_concept_in_sentence(n, key):
                entry["valores"].extend(vals)
            km = re.search(rx, n)
            pct = PCT_RE.search(n[km.end(): km.end() + 20]) if km else None
            if pct and key in PCT_KEYS and "porcentaje" not in entry:
                entry["porcentaje"] = pct.group(1).replace(",", ".") + "%"
            m_months = re.search(r"(\d+|um|uma|dois|duas|tres)\s*(?:\(\w+\)\s*)?(?:meses|mes|alugueis|aluguel)", n)
            if key == "caucao_deposito" and m_months:
                entry["meses"] = _word_to_int(m_months.group(1))
            if key not in RENT_KEYS:
                if NOT_INCLUDED_RE.search(n):
                    entry["incluido"] = False
                elif INCLUDED_RE.search(n) and entry["incluido"] is None:
                    entry["incluido"] = True
            if len(entry["menciones"]) < 2:
                entry["menciones"].append(sent[:220])

    rent = ad.get("alquiler")
    condo = ad.get("condominio")
    iptu = ad.get("iptu")
    declared = {
        "alquiler": rent,
        "condominio": condo,
        "iptu": iptu,
        "total_estimado_olx": ad.get("total_estimado_olx"),
    }
    notas = []
    for label, v in (("condominio", condo), ("IPTU", iptu)):
        if v is not None and 0 < v <= 10:
            notas.append(f"{label} declarado como {_brl(v)} (valor simbólico): probablemente está incluido en el alquiler; confírmalo.")
    base_total = (rent or 0) + (condo or 0) + (iptu or 0) if rent is not None else None

    # alquiler bruto vs líquido (bonificación por pago puntual)
    bruto = items.get("aluguel_bruto", {}).get("valores") or []
    if bruto and rent and max(bruto) > rent * 1.02:
        notas.append(
            f"El precio publicado ({_brl(rent)}) es el alquiler 'líquido' con bonificación por pago puntual; "
            f"el valor de contrato ('bruto') es {_brl(max(bruto))}. El primer mes o cualquier atraso se cobra por el bruto."
        )
    if (condo in (None, 0) or condo <= 10) and "apart" in normalize(ad.get("categoria") or ad.get("tipo_inmueble") or ""):
        if "condominio" in items and items["condominio"]["incluido"]:
            notas.append("El texto indica que el condominio está incluido en el alquiler.")
        else:
            notas.append("Apartamento con condominio = R$ 0 o sin informar: confirma si hay cuota de condominio.")
    if iptu in (None, 0) and not ("iptu" in items and items["iptu"]["incluido"]):
        notas.append("IPTU en R$ 0 o sin informar: pregunta si existe y si se paga en cuotas mensuales.")
    if any(k in items for k in ("taxa_contrato_cadastro", "corretagem")):
        notas.append(
            "Se mencionan tasas de contrato/intermediación. En Brasil la comisión del corretor normalmente la paga el "
            "propietario (Lei 8.245/91, art. 22); pregunta el detalle antes de firmar."
        )

    no_fiador = re.search(r"sem fiador|dispensa fiador|nao precisa (?:de )?fiador", normalize(desc))
    extras = [lbl for k, lbl in EXTRA_MONTHLY.items() if k in items and items[k]["incluido"] is not True]
    if extras:
        notas.append(
            "Además de alquiler+condominio+IPTU, el texto menciona otros cargos que NO están en el total de OLX: "
            + ", ".join(extras) + ". Pide el valor exacto de cada uno."
        )
    # condominio/IPTU ya están en la tabla: solo se listan si el texto aporta valor o inclusión
    for k in ("condominio", "iptu"):
        if k in items and not items[k]["valores"] and items[k]["incluido"] is None:
            del items[k]
    garantias = [k for k in items if k in GUARANTEE_CONCEPTS and not (k == "fiador" and no_fiador)]
    if no_fiador and "fiador" in items and not items["fiador"]["valores"]:
        del items["fiador"]
    return {
        "declarado_en_olx": declared,
        "total_mensual_base": base_total,
        "conceptos_en_texto": list(items.values()),
        "garantias_mencionadas": garantias,
        "sin_fiador_mencionado": bool(no_fiador),
        "notas": notas,
    }


def _only_concept_in_sentence(n: str, key: str) -> bool:
    """Evita asignar el mismo R$ a varios conceptos cuando la frase mezcla varios."""
    hits = sum(1 for k, rx in COST_CONCEPTS if re.search(rx, n))
    return hits <= 1 or key in ("aluguel_bruto", "aluguel_liquido", "bonificacao_pontualidade")


def _word_to_int(w: str) -> int | None:
    m = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3}
    return int(w) if w.isdigit() else m.get(w)


def _brl(v: float | None) -> str:
    from .parsers import fmt_brl

    return fmt_brl(v)


# ---------------------------------------------------------------------------
# 2) Contactos que aparecen en el texto
# ---------------------------------------------------------------------------

PHONE_RE = re.compile(r"(?<!\d)(?:\+?55[\s.-]?)?(?:\(?\d{2}\)?[\s.-]?)?9?\d{4}[\s.-]?\d{4}(?!\d)")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"]+|\b[\w-]+\.(?:com|com\.br|net|br|link|site|app)(?:/[^\s]*)?\b", re.I)
INSTAGRAM_RE = re.compile(r"\b(?:instagram|insta|ig)\b\s*[:\-]?\s*@?([A-Za-z0-9_.]{3,30})|(?<![\w@])@([A-Za-z0-9_.]{3,30})\b", re.I)
WHATS_RE = re.compile(r"whats\s*app|whatsapp|\bwhats\b|\bzap\b|\bwpp\b|\bzapzap\b", re.I)
NUM_WORDS = {"zero", "um", "dois", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove", "meia"}
CRECI_RE = re.compile(r"creci[\s:/-]*(?:[a-z]{2}[\s:/-]*)?(?:n[ºo°.]?\s*)?([0-9][0-9.\-]{2,}[a-z]?)", re.I)


def extract_contacts(ad: dict) -> dict:
    text = f"{ad.get('titulo') or ''}\n{ad.get('descripcion') or ''}"
    phones = []
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 8 <= len(digits) <= 13 and not _looks_like_price_or_cep(text, m):
            phones.append(m.group(0).strip())
    # números escritos con palabras ("nove nove oito ...")
    words = normalize(text).split()
    run, spelled = [], []
    for w in words + ["_"]:
        if w.strip(".,;:-") in NUM_WORDS:
            run.append(w.strip(".,;:-"))
        else:
            if len(run) >= 6:
                spelled.append(" ".join(run))
            run = []
    insta = [a or b for a, b in INSTAGRAM_RE.findall(text) if (a or b) and "@" not in (a or b)]
    emails = EMAIL_RE.findall(text)
    urls = [u for u in URL_RE.findall(text) if "@" not in u and not any(u in e for e in emails)]
    tel = ad.get("telefono") or {}
    anun = ad.get("anunciante") or {}
    return {
        "telefonos_en_texto": sorted(set(phones)),
        "numeros_escritos_con_palabras": spelled,
        "emails_en_texto": sorted(set(emails)),
        "links_en_texto": sorted(set(urls)),
        "instagram": sorted(set(insta)),
        "menciona_whatsapp": bool(WHATS_RE.search(text)),
        "creci": sorted(set(CRECI_RE.findall(text))),
        "telefono_en_olx": {
            "registrado": tel.get("tiene_telefono"),
            "verificado_por_olx": tel.get("verificado"),
            "digitos_visibles": tel.get("parcial"),
            "como_verlo": "Botón 'Ver telefone' / 'Ligar' en la página del anuncio (OLX lo revela solo ahí).",
        },
        "chat_olx_habilitado": anun.get("chat_habilitado"),
        "whatsapp_olx_habilitado": anun.get("whatsapp_habilitado"),
    }


def _looks_like_price_or_cep(text: str, m: re.Match) -> bool:
    before = text[max(0, m.start() - 6): m.start()].lower()
    if "r$" in before or "cep" in text[max(0, m.start() - 8): m.start()].lower():
        return True
    raw = m.group(0)
    return bool(re.fullmatch(r"\d{5}-?\d{3}", raw.strip()))


# ---------------------------------------------------------------------------
# 3) Dirección
# ---------------------------------------------------------------------------

_STREET_KW = r"\b(?i:rua|r\.|avenida|av\.?|alameda|al\.|travessa|tv\.|rodovia|estrada|pra[çc]a|largo|servid[aã]o)\s+"
_STREET_NAME = r"[A-ZÀ-Úa-zà-ú0-9][\wÀ-ú'.\- ]{2,50}?"
STREET_NUM_RE = re.compile(_STREET_KW + _STREET_NAME + r"\s*,?\s*(?:n[ºo°.]?\s*)?(?:\d{1,2}\.\d{3}|\d{1,5})(?![\d])")
STREET_RE = re.compile(_STREET_KW + _STREET_NAME + r"(?=\s*(?:[,.;\n\-–(]|$)| (?:no|na|em|bairro|pr[óo]x|perto|esquina)\b)")


def _find_streets(text: str) -> list[str]:
    out: list[str] = []
    for rx in (STREET_NUM_RE, STREET_RE):
        for m in rx.finditer(text):
            st = m.group(0).strip(" ,.-")
            if not any(st in o or o in st for o in out):
                out.append(st)
    return out


NEAR_RE = re.compile(r"(?:pr[oó]x(?:imo|ima|\.)?|perto|em frente|a \d+ ?(?:m|metros|min(?:utos)?|quadras?)) (?:a|ao|à|do|da|de|dos|das)?\s*([^.,;\n]{3,60})", re.I)
BAIRRO_TEXT_RE = re.compile(r"(?:bairro|no|na|em)\s+([A-ZÀ-Ú][\wÀ-ú]+(?:\s+(?:da|do|de|dos|das)?\s*[A-ZÀ-Ú][\wÀ-ú]+){0,3})\s*(?:[,\-–/]\s*Curitiba|[,\-–/]\s*[A-Z]{2}\b)")


def extract_address(ad: dict, cep_info: dict | None = None) -> dict:
    loc = ad.get("ubicacion") or {}
    text = f"{ad.get('titulo') or ''}\n{ad.get('descripcion') or ''}"
    streets = _find_streets(text)
    near = []
    for n in NEAR_RE.findall(text):
        n = re.sub(r"^(?:o|a|os|as|ao|à|aos|e|de|do|da)\s+", "", n.strip(), flags=re.I)
        n = re.split(r"\s+r\$|\s+\d+[.,]\d", n)[0].strip()
        if len(n) >= 3 and n not in near:
            near.append(n)
    near = near[:5]
    declared = normalize(loc.get("barrio"))
    mentioned = []
    for b in BAIRRO_TEXT_RE.findall(text):
        nb = normalize(b)
        if nb and nb != declared and nb not in ("curitiba",) and len(nb) > 3:
            mentioned.append(b)
    exact = bool(loc.get("direccion_completa_publica"))
    return {
        "barrio_declarado": loc.get("barrio"),
        "municipio": loc.get("municipio"),
        "uf": loc.get("uf"),
        "cep": loc.get("cep"),
        "direccion_olx": loc.get("direccion_olx"),
        "precision": "exacta (el anunciante publicó la dirección)" if exact
        else "aproximada: OLX muestra la calle/tramo del CEP, no el número exacto",
        "calle_segun_cep": cep_info,
        "direcciones_en_texto": streets[:5],
        "referencias_cercanas": near,
        "otros_barrios_mencionados": sorted(set(mentioned))[:5],
        "mapa_aprox": (
            f"https://www.google.com/maps/search/?api=1&query={loc.get('lat')},{loc.get('lon')}"
            if loc.get("lat") and loc.get("lon") else None
        ),
    }


# ---------------------------------------------------------------------------
# 4) ¿Directo con el dueño?
# ---------------------------------------------------------------------------

OWNER_PHRASES = r"direto com (?:o |a )?(?:proprietari|dono)|direto (?:do|da) (?:proprietari|dono)|sem imobiliaria|sem intermedia|sem corretor|sou (?:o |a )?(?:proprietari|dona?)\b|nao sou corretor|trato direto"
OWNER_NEG = r"nao (?:alugo|trabalho|aceito|quero|tenho interesse|atendo|negocio)\s(?:\w+\s){0,3}?(?:imobiliaria|corretor|intermediari)\w*|(?:imobiliarias?|corretores?) nao\b"
BROKER_PHRASES = r"\bcreci\b|imobiliaria|corretor(?:a)?\b|corretagem|codigo do anuncio|\bref(?:erencia)?[.:]?\s*\w*\d|administradora|imoveis\b|negocios imobiliarios|consultor imobiliario"
BROKER_NAME = r"imove|imobili|corretor|negocios|realty|consultoria|administradora|ltda|\beireli\b|\bme\b|empreendimentos|\bimob\b"


def owner_assessment(ad: dict, seller: dict | None) -> dict:
    text = normalize(f"{ad.get('titulo')}\n{ad.get('descripcion')}")
    anun = ad.get("anunciante") or {}
    name = normalize(anun.get("nombre"))
    pro = bool(anun.get("profesional") or anun.get("cuenta_pro") or (seller or {}).get("es_profesional"))
    evid, contra = [], []
    if pro:
        evid.append("OLX marca el anuncio/cuenta como PROFESIONAL (inmobiliaria o corretor).")
    else:
        evid.append("OLX marca el anuncio como PARTICULAR (persona física).")
    if re.search(OWNER_PHRASES, text) or re.search(OWNER_NEG, text):
        evid.append("El texto dice que es directo con el propietario / no trabaja con inmobiliarias.")
    text_wo_neg = re.sub(OWNER_NEG, " ", text)
    if re.search(BROKER_PHRASES, text_wo_neg):
        contra.append("El texto menciona CRECI, inmobiliaria, corretor o código de referencia.")
    if re.search(BROKER_NAME, name):
        contra.append(f"El nombre del anunciante ('{anun.get('nombre')}') parece de empresa/inmobiliaria.")
    if (seller or {}).get("creci") and not pro:
        contra.append(f"El perfil del anunciante informa CRECI ({seller['creci']}): es corretor/inmobiliaria.")
    if anun.get("plan_activo"):
        contra.append(f"La cuenta tiene un plan comercial activo ({anun.get('plan_activo')}).")
    if ad.get("zap_listing_id"):
        contra.append("El anuncio está sincronizado con ZAP/VivaReal (típico de inmobiliarias).")

    if pro:
        verdict, prob = "Inmobiliaria / corretor", "baja"
    elif contra:
        verdict, prob = "Particular, pero con señales de intermediario", "media"
    else:
        verdict, prob = "Particular (probablemente el propio dueño)", "alta"
    return {
        "veredicto": verdict,
        "probabilidad_trato_directo_con_dueno": prob,
        "a_favor": evid,
        "en_contra": contra,
        "nota": "Confírmalo pidiendo la matrícula actualizada del inmueble (Cartório de Registro de Imóveis) "
                "y verificando que el nombre del propietario coincide con quien firma el contrato.",
    }


# ---------------------------------------------------------------------------
# 5) Mercado
# ---------------------------------------------------------------------------

def market_stats(items: list[dict], exclude_list_id: int | None = None) -> dict | None:
    rents, totals, per_m2 = [], [], []
    for it in items:
        if exclude_list_id and it.get("list_id") == exclude_list_id:
            continue
        r = it.get("alquiler")
        if not r or r < 250 or r > 60000:
            continue
        rents.append(r)
        totals.append(r + (it.get("condominio") or 0) + (it.get("iptu") or 0))
        a = it.get("area_m2")
        if a and 10 <= a <= 2000:
            per_m2.append(r / a)
    if len(rents) < 5:
        return None
    q = statistics.quantiles(rents, n=4) if len(rents) >= 4 else [min(rents), statistics.median(rents), max(rents)]
    return {
        "muestra": len(rents),
        "mediana_alquiler": round(statistics.median(rents), 2),
        "p25_alquiler": round(q[0], 2),
        "p75_alquiler": round(q[2], 2),
        "mediana_total_mensual": round(statistics.median(totals), 2),
        "mediana_precio_m2": round(statistics.median(per_m2), 2) if len(per_m2) >= 5 else None,
        "muestra_m2": len(per_m2),
    }


def price_vs_market(ad: dict, stats: dict | None) -> dict | None:
    if not stats or not ad.get("alquiler"):
        return None
    rent = ad["alquiler"]
    area = ad.get("area_m2")
    if stats.get("mediana_precio_m2") and area and 10 <= area <= 2000:
        ratio = (rent / area) / stats["mediana_precio_m2"]
        base = "precio por m²"
    else:
        ratio = rent / stats["mediana_alquiler"]
        base = "alquiler mediano"
    return {"ratio": round(ratio, 2), "base": base, "diferencia_pct": round((ratio - 1) * 100)}


# ---------------------------------------------------------------------------
# 6) Riesgo de fraude
# ---------------------------------------------------------------------------

SCAM_PATTERNS: list[tuple[str, int, str]] = [
    (r"(?:deposit|pix|transfer|sinal|reserva|adiant|antecip|pagar?)\w*.{0,50}(?:antes (?:da|de) (?:visita|ver|conhecer)|para (?:reservar|garantir|segurar)|garantir (?:o|a) (?:imovel|vaga|apartamento|casa))", 30,
     "Pide pago/depósito/PIX para reservar o antes de visitar."),
    (r"(?:moro|morando|estou|resido|residindo|trabalho|trabalhando|mudei)\s.{0,25}(?:fora do (?:pais|brasil)|no exterior|em outro estado|em outra cidade|portugal|europa|estados unidos|\beua\b|canada|japao|a trabalho)", 25,
     "El 'dueño' dice vivir o estar fuera (no puede mostrar el inmueble)."),
    (r"(?:chave|chaves).{0,40}(?:correio|sedex|transportadora|motoboy|entreg\w* (?:em|na) (?:sua )?casa)|envio (?:as|a) chave", 25,
     "Ofrece enviar las llaves por correo/mensajero."),
    (r"nao (?:posso|consigo|da para|tem como) (?:mostrar|fazer visita|visitar|agendar visita)|sem (?:necessidade de )?visita|visita (?:somente|so) apos (?:o )?pagamento", 25,
     "Evita o condiciona la visita."),
    (r"airbnb|booking\.com|pagamento (?:pelo|via) (?:site|link)|link de pagamento|olx pay.{0,20}(?:aluguel|reserva)", 15,
     "Menciona pago por link/plataforma externa."),
    (r"urgente|muitos interessados|varios interessados|primeiro que (?:pagar|depositar|fechar)|so hoje|ultima unidade|quem chegar primeiro", 8,
     "Presión/urgencia para decidir rápido."),
    (r"(?:enviar|mande|mandar|envie)\s.{0,30}(?:rg|cpf|documentos?|comprovante de renda|holerite).{0,30}(?:whats|e-?mail|antes)", 8,
     "Pide documentos personales por fuera de OLX antes de visitar."),
    (r"contrato (?:por|via|pelo) (?:e-?mail|whats)|assinatura (?:digital|online) (?:antes|sem visita)", 10,
     "Propone cerrar contrato a distancia sin visita."),
    (r"(?:so|somente|apenas) (?:pelo |por )?(?:whats|zap|wpp|e-?mail)|chama no (?:whats|zap)|me chame no (?:whats|zap)|contato (?:so |somente )?(?:pelo|por) (?:whats|zap)", 8,
     "Empuja a sacar la conversación fuera de OLX."),
]


def fraud_risk(ad: dict, seller: dict | None, contacts: dict, address: dict,
               owner: dict, market_cmp: dict | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    text = normalize(f"{ad.get('titulo')}\n{ad.get('descripcion')}")
    red: list[dict] = []
    green: list[str] = []

    def add(points: int, msg: str, nivel: str | None = None):
        red.append({"puntos": points, "senal": msg, "gravedad": nivel or ("alta" if points >= 20 else "media" if points >= 8 else "baja")})

    # --- texto ---
    for rx, pts, msg in SCAM_PATTERNS:
        if re.search(rx, text):
            add(pts, msg)

    # --- precio ---
    rent = ad.get("alquiler")
    if market_cmp:
        r = market_cmp["ratio"]
        if r < 0.55:
            add(28, f"Precio MUY por debajo del mercado ({market_cmp['diferencia_pct']}% vs {market_cmp['base']} de la zona).")
        elif r < 0.72:
            add(14, f"Precio bastante por debajo del mercado ({market_cmp['diferencia_pct']}% vs {market_cmp['base']} de la zona).")
    if rent is not None:
        if rent > 60000:
            add(6, "Precio incompatible con alquiler mensual (¿precio de venta mal categorizado?).")
        elif rent < 250 and normalize(ad.get("categoria") or "") in ("apartamentos", "casas"):
            add(10, "Precio irrealmente bajo para alquiler mensual (¿diaria, temporada, cebo?).")

    # --- anunciante ---
    if seller:
        created = _parse_dt(seller.get("cuenta_creada"))
        age_days = (now - created).days if created else None
        if seller.get("cuenta_nueva") or (age_days is not None and age_days < 30):
            add(22, f"Cuenta de OLX nueva ({age_days if age_days is not None else '<30'} días).")
        elif age_days is not None and age_days < 180:
            add(8, f"Cuenta de OLX reciente ({age_days} días).")
        elif age_days is not None and age_days > 3 * 365:
            green.append(f"Cuenta con {age_days // 365} años en OLX.")
        if seller.get("identidad_verificada"):
            green.append("Identidad verificada por OLX (validación facial/documento).")
        elif not (ad.get("anunciante") or {}).get("profesional"):
            add(8, "Identidad del particular NO verificada por OLX.")
        if not seller.get("telefono_verificado"):
            add(6, "Teléfono de la cuenta no verificado.")
        if not seller.get("email_verificado"):
            add(3, "E-mail de la cuenta no verificado.")
        sl = seller.get("ubicacion_anunciante") or {}
        ad_uf = (ad.get("ubicacion") or {}).get("uf")
        if sl.get("state") and ad_uf and sl["state"] != ad_uf and not (ad.get("anunciante") or {}).get("profesional"):
            add(12, f"El anunciante está registrado en otro estado ({sl.get('city')}/{sl['state']}) distinto al del inmueble ({ad_uf}).")
        if seller.get("reputacion"):
            green.append(f"Reputación OLX: {seller['reputacion']}.")
        if seller.get("creci"):
            green.append(f"CRECI informado en el perfil: {seller['creci']}.")
    else:
        add(0, "No se pudo consultar el perfil del anunciante (antigüedad/verificaciones).", "info")

    if owner.get("probabilidad_trato_directo_con_dueno") == "media":
        add(4, "Se presenta como particular pero hay señales de intermediario.")

    # --- calidad del anuncio ---
    fotos = ad.get("fotos") or 0
    if fotos == 0:
        add(15, "Sin fotos.")
    elif fotos < 4:
        add(7, f"Muy pocas fotos ({fotos}).")
    desc_len = len(ad.get("descripcion") or "")
    if desc_len < 60:
        add(4, "Descripción muy corta o vacía.")
    if contacts.get("telefonos_en_texto") or contacts.get("numeros_escritos_con_palabras") or contacts.get("emails_en_texto"):
        add(6, "Pone teléfono/e-mail en el texto (común en estafas para sacar la conversación de OLX; también lo hacen anunciantes legítimos).")
    if contacts.get("numeros_escritos_con_palabras"):
        add(8, "Escribe el número con palabras para evadir el filtro de OLX.")
    if address.get("otros_barrios_mencionados"):
        add(4, f"El texto menciona otro barrio ({', '.join(address['otros_barrios_mencionados'][:2])}) distinto al declarado ({address.get('barrio_declarado')}).")
    if (ad.get("anunciante") or {}).get("profesional") and contacts.get("creci"):
        green.append("El anuncio informa número de CRECI (verificable en crecipr.gov.br o el CRECI del estado).")
    if ad.get("zap_listing_id"):
        green.append("Anuncio sincronizado desde ZAP/VivaReal (feed de inmobiliaria).")

    score = sum(r["puntos"] for r in red)
    score -= 6 * len([g for g in green if "años" in g or "Identidad" in g])
    score = max(0, min(100, score))
    nivel = "ALTO" if score >= 50 else "MEDIO" if score >= 25 else "BAJO"
    return {
        "puntaje": score,
        "nivel": nivel,
        "senales_de_alerta": sorted(red, key=lambda r: -r["puntos"]),
        "senales_positivas": green,
        "aviso": "Puntaje heurístico basado en patrones conocidos del 'golpe do aluguel'. "
                 "Un puntaje bajo NO garantiza que sea seguro.",
    }


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


CHECKLIST = [
    "No pagues nada (sinal, reserva, caução, PIX) antes de visitar el inmueble en persona.",
    "Pide la certidão de matrícula actualizada (Cartório de Registro de Imóveis) y confirma el nombre del propietario.",
    "El contrato debe estar a nombre del propietario o de una inmobiliaria con CRECI activo; el pago, a una cuenta con ese mismo titular.",
    "Si es inmobiliaria/corretor, verifica el CRECI en el sitio del CRECI del estado (PR: crecipr.gov.br).",
    "Haz una búsqueda inversa de las fotos (Google Imágenes/Lens) para ver si aparecen en otros anuncios.",
    "Confirma condominio e IPTU con la administradora del edificio o la boleta de IPTU.",
    "Mantén la conversación en el chat de OLX hasta confirmar que el anuncio es real.",
]


def questions_to_ask(costs: dict, owner: dict) -> list[str]:
    qs = ["¿Cuándo puedo visitar el inmueble?"]
    if not costs.get("garantias_mencionadas"):
        qs.append("¿Qué garantía piden (caução, fiador, seguro-fiança, título de capitalização)?")
    qs.append("¿Qué gastos iniciales hay además del primer alquiler (tasas de contrato, seguro incendio, vistoria)?")
    qs.append("¿El condominio incluye agua/gas? ¿El IPTU se paga en cuotas?")
    if owner.get("probabilidad_trato_directo_con_dueno") != "baja":
        qs.append("¿Usted es el propietario que figura en la matrícula del inmueble?")
    return qs
