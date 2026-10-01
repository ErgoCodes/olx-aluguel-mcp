import json, pathlib, sys
from datetime import datetime, timezone
sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "src"))
from olx_aluguel_mcp import parsers, analysis, client as c

F = pathlib.Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 25, tzinfo=timezone.utc)
SELLER_OK = {"cuenta_creada": "2015-02-06T16:38:33Z", "cuenta_nueva": False, "es_profesional": True, "identidad_verificada": False,
             "telefono_verificado": True, "email_verificado": True, "reputacion": "Intermediário", "ubicacion_anunciante": None, "creci": None}
SELLER_BAD = {"cuenta_creada": "2026-09-20T10:00:00Z", "cuenta_nueva": True, "es_profesional": False, "identidad_verificada": False,
              "telefono_verificado": False, "email_verificado": False, "ubicacion_anunciante": {"city": "São Paulo", "state": "SP"}, "creci": None}

def load(n): return (F / n).read_text(encoding="utf-8")

def run(ad, seller, market=None):
    costs = analysis.extract_costs(ad); ct = analysis.extract_contacts(ad); addr = analysis.extract_address(ad)
    own = analysis.owner_assessment(ad, seller); cmp_ = analysis.price_vs_market(ad, market)
    return costs, ct, addr, own, analysis.fraud_risk(ad, seller, ct, addr, own, cmp_, now=NOW)

def test_parse_ad_pro():
    ad = parsers.parse_ad_page(load("ad_pro.html"))
    assert ad["list_id"] == 1538924824 and ad["alquiler"] == 1850 and ad["condominio"] == 370 and ad["iptu"] == 58
    assert ad["total_estimado_olx"] == 2278 and ad["area_m2"] == 35 and ad["habitaciones"] == 1 and ad["fotos"] == 20
    assert ad["anunciante"]["profesional"] and ad["ubicacion"]["cep"] == "82590300"
    assert "Aluguel Bruto" in ad["descripcion"] and "<br>" not in ad["descripcion"]

def test_costs_pro():
    ad = parsers.parse_ad_page(load("ad_pro.html"))
    costs, ct, addr, own, risk = run(ad, SELLER_OK)
    keys = {x["concepto"]: x for x in costs["conceptos_en_texto"]}
    assert keys["aluguel_bruto"]["valores"] == [2312.5]
    for k in ("seguro_incendio", "fundo_conservacao", "despesas_bancarias", "bonificacao_pontualidade"):
        assert k in keys, k
    assert any("bruto" in n for n in costs["notas"])
    assert costs["total_mensual_base"] == 2278
    assert own["probabilidad_trato_directo_con_dueno"] == "baja"
    assert risk["nivel"] == "BAJO", risk

def test_scam():
    ad = parsers.parse_ad_page(load("ad_scam.html"))
    market = {"mediana_alquiler": 1900, "mediana_precio_m2": 40.0}
    costs, ct, addr, own, risk = run(ad, SELLER_BAD, market)
    assert risk["nivel"] == "ALTO" and risk["puntaje"] >= 80, risk
    txt = " ".join(s["senal"] for s in risk["senales_de_alerta"])
    for w in ("antes de visitar", "fuera", "llaves", "mercado", "nueva", "otro estado", "palabras"):
        assert w in txt, w
    assert "(41) 99876-5432" in ct["telefonos_en_texto"]
    assert ct["emails_en_texto"] == ["dono.apto@gmail.com"] and ct["menciona_whatsapp"]
    assert ct["numeros_escritos_con_palabras"]
    assert any("XV de Novembro" in s for s in addr["direcciones_en_texto"]), addr
    assert "Batel" in addr["otros_barrios_mencionados"], addr
    keys = {x["concepto"]: x for x in costs["conceptos_en_texto"]}
    assert keys["agua"]["incluido"] is True and keys["internet"]["incluido"] is True
    assert keys["caucao_deposito"].get("meses") == 2
    assert costs["sin_fiador_mencionado"]
    assert own["probabilidad_trato_directo_con_dueno"] == "alta"

def test_search():
    res = parsers.parse_search_page(load("search.html"))
    assert res["total"] == 24 and len(res["anuncios"]) == 9
    a = res["anuncios"][0]
    assert a["alquiler"] == 1850 and a["total_estimado"] == 2278 and a["precio_m2"] == round(1850 / 35, 2) and a["profesional"]
    assert res["anuncios"][2]["habitaciones"] == 5 and res["anuncios"][2]["precio_anterior"] == 3000
    st = analysis.market_stats(res["anuncios"])
    assert st and st["muestra"] == 9

def test_urls():
    u = c.build_search_url("estado-pr/regiao-de-curitiba-e-paranagua/boa-vista/taruma", tipo="apartamentos", precio_max=2500,
                           habitaciones=[1, 2], anunciante="particular", caracteristicas=["mobiliado"], condominio=["aceita_pet"],
                           ordenar="recientes", pagina=2)
    assert u == ("https://www.olx.com.br/imoveis/aluguel/apartamentos/estado-pr/regiao-de-curitiba-e-paranagua/boa-vista/taruma"
                 "?pe=2500&ros=1&ros=2&f=p&rfs=109&rcf=204&sf=1&o=2"), u
    assert c.ad_url("1538924824") == "https://www.olx.com.br/vi/1538924824"
    assert c.ad_url("https://pr.olx.com.br/x/imoveis/y-1538924824?lis=listing_1002") == "https://pr.olx.com.br/x/imoveis/y-1538924824"
    assert c.with_page("https://www.olx.com.br/a?o=3&pe=1", 5) == "https://www.olx.com.br/a?pe=1&o=5"
    ad = parsers.parse_ad_page(load("ad_pro.html"))
    assert c.market_location_for_ad(ad) == "estado-pr/regiao-de-curitiba-e-paranagua/boa-vista"

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)


def _ad(desc, rent=1500.0, condo=None, iptu=None, pro=False, name="Maria"):
    return {"titulo": "Apto", "descripcion": desc, "alquiler": rent, "condominio": condo, "iptu": iptu, "categoria": "Apartamentos",
            "anunciante": {"nombre": name, "profesional": pro}, "ubicacion": {"barrio": "Tarumã"}, "telefono": {}, "fotos": 10}

def test_text_rules():
    # caução sin "R$" + meses derivados del alquiler
    k = {x["concepto"]: x for x in analysis.extract_costs(_ad("- caução de 1200,00\n- água, luz e internet incluso no valor", rent=1200))["conceptos_en_texto"]}
    assert k["caucao_deposito"]["valores"] == [1200.0] and k["caucao_deposito"]["meses"] == 1
    assert k["luz"]["incluido"] and k["internet"]["incluido"]
    # el valor del alquiler no se asigna al condominio
    k = {x["concepto"]: x for x in analysis.extract_costs(_ad("Valor do aluguel: R$ 3.200,00 mensais, com condomínio incluso.", rent=3200))["conceptos_en_texto"]}
    assert k["condominio"]["valores"] == [] and k["condominio"]["incluido"] is True
    # valores simbólicos
    assert any("simbólico" in n for n in analysis.extract_costs(_ad("x", condo=1.0, iptu=1.0))["notas"])
    # negación de inmobiliaria => dueño
    own = analysis.owner_assessment(_ad("Não alugo por imobiliária, tratar com o proprietário."), None)
    assert own["probabilidad_trato_directo_con_dueno"] == "alta" and not own["en_contra"]
    # CRECI en el perfil de un "particular"
    own = analysis.owner_assessment(_ad("Studio"), {"creci": "J4948"})
    assert own["probabilidad_trato_directo_con_dueno"] == "media"
    # "Igreja" no es Instagram
    assert analysis.extract_contacts(_ad("próximo à Igreja das Vitórias"))["instagram"] == []
    assert analysis.extract_contacts(_ad("insta: @apto.curitiba"))["instagram"] == ["apto.curitiba"]
