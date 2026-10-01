"""Genera fixtures HTML con el mismo formato que las páginas reales de OLX (sep/2026)."""
import html, json, pathlib
F = pathlib.Path(__file__).parent / "fixtures"

DESC_PRO = ("Código do anúncio: 1963<br><br>ESPECIALE ALUGA : O Studio em estado de zero e totalmente novo, perfeito para quem busca viver com praticidade e comodidade, a sua localização é excelente e possui fácil acesso a variados locais seja utilizando transporte público ou se deslocando a pé. O imóvel está totalmente mobiliado, pronto para se mudar!<br><br>O condomínio dispõe de Portaria 24 horas- 2 elevadores- Lavanderia Coletiva-Mercado Express.    <br><br>Obs: Prédio não dispõe de vaga de garagem, porém possui um estacionamento ao lado com convênio para moradores.<br><br>Valores e Condições para Locação:<br><br>Aluguel Bruto: R$ 2.312,50 + taxas.<br>Bonificação para pagamento em dia: R$ 462,50(*)<br>Aluguel Líquido: R$ 1.850,00 + taxas.<br><br>* A bonificação será concedida a partir do 2º mês de locação, para pagamento em dia (+) as taxas. Os primeiros 30 dias serão contabilizados pelo valor bruto + taxas.<br>* Taxas mensais são:<br>Seguro Incêndio, IPTU, Condomínio, despesas Bancarias, FCI de 5% (Fundo de Conservação do imóvel, que será devolvido ao final do contrato de locação ou entrega do imóvel, caso não seja necessário reparos/ consertos)<br>*Todos sujeitos a atualização de valores.<br><br>O valor do condomínio informado refere-se a estimativa do valor da cota, sem consumos individuais, valores do anuncio ou disponibilidade do imóvel podem ser alterados sem aviso prévio.<br><br>Maiores informações:<br>41 |")

def props(d):
    return [{"label": l, "name": n, "url": None, "value": v, "values": None} for n, l, v in d]

def rep(rent, condo, iptu, total):
    return [
        {"isTotalPrice": None, "label": "Aluguel", "name": "Aluguel", "period": "mês", "tooltip": None, "value": rent},
        {"isTotalPrice": None, "label": "Condomínio", "name": "condominio", "period": "mês", "tooltip": None, "value": condo},
        {"isTotalPrice": None, "label": "IPTU", "name": "iptu", "period": None, "tooltip": "Consulte...", "value": iptu},
        {"isTotalPrice": True, "label": "Valor total previsto", "name": "estimated_monthly_cost", "period": "mês", "tooltip": "É uma estimativa...", "value": total},
    ]

def ad_page(ad):
    data = {"ad": ad, "urls": {}, "deviceType": "desktop"}
    attr = html.escape(json.dumps(data, ensure_ascii=False), quote=True)
    ld = json.dumps({"@context": "https://schema.org", "@type": "RentAction", "identifier": ad["listId"]}, ensure_ascii=False)
    return (f'<!DOCTYPE html><html><head><title>{html.escape(ad["subject"])} | OLX</title>'
            f'<style>.x{{bottom:var(--spacing-1)}}</style><script id="initial-data" type="text/plain" data-json="{attr}"></script>'
            f'<script type="application/ld+json">{ld}</script></head><body></body></html>')

pro = {
    "adId": 1812923419, "listId": 1538924824, "subject": "STUDIO TOTALMENTE MOBILIADO NO CENTRO DE CURITIBA -PROX.SHOPPING CURITIBA",
    "body": DESC_PRO, "description": DESC_PRO, "category": 1020, "categoryName": "Apartamentos", "parentCategoryName": "Imóveis",
    "friendlyUrl": "https://pr.olx.com.br/regiao-de-curitiba-e-paranagua/imoveis/studio-totalmente-mobiliado-no-centro-de-curitiba-prox-shopping-curitiba-1538924824",
    "price": "R$ 1.850", "priceValue": "R$ 1.850", "oldPrice": None, "priceLabel": "Aluguel", "professionalAd": True,
    "listTime": "2026-09-25T22:39:50.000Z", "origListTime": 1790375990, "chatEnabled": True,
    "images": [{"original": f"https://img.olx.com.br/images/31/31864832204110{i}.jpg"} for i in range(20)], "videos": [],
    "location": {"address": None, "ddd": "41", "mapLati": -25.428618, "mapLong": -49.228481, "municipality": "Curitiba", "municipalityId": 7462,
                 "neighbourhood": "Tarumã", "neighbourhoodId": 38110, "region": "Curitiba e região, PR", "uf": "PR", "zipcode": "82590300", "zone": "boa-vista", "zoneId": 491},
    "properties": props([("category", "Categoria", "Apartamentos"), ("real_estate_type", "Tipo", "Aluguel - loft/studio"), ("condominio", "Condomínio", "R$ 370"),
                         ("iptu", "IPTU", "R$ 58"), ("size", "Área útil", "35m²"), ("rooms", "Quartos", "1"), ("bathrooms", "Banheiros", "1"),
                         ("re_features", "Detalhes do imóvel", "Mobiliado"), ("re_complex_features", "Detalhes do condomínio", "Condomínio fechado, Elevador, Salão de festas"), ("re_types", "Tipo", "Loft")]),
    "realEstatePriceInfo": rep("R$ 1.850", "R$ 370", "R$ 58", "R$ 2.278"),
    "phone": {"maskedPhone": "4130247...", "phone": "", "phoneExist": True, "phoneHidden": False, "phoneVerified": True},
    "user": {"configs": {"activePlan": "\"SUBSCRIPTION_ZAP_500000\"", "proAccount": True, "showFullAddress": False, "whatsapp": False},
             "name": "Especiale Imóveis", "publicAccountId": "31ae5377-4379-4cc0-aabf-1014df47359b", "userId": 115139873, "whatsapp": {"enabled": None}},
    "zapListingId": "2914340841", "isFeatured": False, "denounceLink": "https://denuncia.olx.com.br/report?from=web&data=x",
}
(F / "ad_pro.html").write_text(ad_page(pro), encoding="utf-8")

SCAM = ("Apartamento lindo 2 quartos mobiliado, direto com o proprietário, sem fiador!<br>"
        "Estou morando em Portugal a trabalho por isso não posso mostrar pessoalmente.<br>"
        "Para reservar é necessário um depósito via PIX de R$ 800 antes da visita, as chaves envio pelo correio.<br>"
        "Muitos interessados, urgente! Chama no whats quatro um nove nove oito sete seis cinco quatro três ou (41) 99876-5432<br>"
        "email: dono.apto@gmail.com<br>Água e internet inclusos. Caução de 2 meses.<br>Fica na Rua XV de Novembro, 1200 - bairro Batel, Curitiba")
scam = json.loads(json.dumps(pro))
scam.update({
    "adId": 1, "listId": 1599999999, "subject": "Apto 2 quartos mobiliado Tarumã - barato", "body": SCAM, "description": SCAM,
    "friendlyUrl": "https://pr.olx.com.br/regiao-de-curitiba-e-paranagua/imoveis/apto-2-quartos-mobiliado-taruma-barato-1599999999",
    "price": "R$ 700", "priceValue": "R$ 700", "professionalAd": False, "images": [{"original": "https://img.olx.com.br/images/1/1.jpg"}] * 2,
    "properties": props([("category", "Categoria", "Apartamentos"), ("real_estate_type", "Tipo", "Aluguel - apartamento padrão"), ("condominio", "Condomínio", "R$ 0"),
                         ("iptu", "IPTU", "R$ 0"), ("size", "Área útil", "60m²"), ("rooms", "Quartos", "2"), ("bathrooms", "Banheiros", "1")]),
    "realEstatePriceInfo": rep("R$ 700", "R$ 0", "R$ 0", "R$ 700"),
    "phone": {"maskedPhone": "", "phone": "", "phoneExist": False, "phoneHidden": True, "phoneVerified": False},
    "user": {"configs": {"proAccount": False, "showFullAddress": False, "whatsapp": False}, "name": "Carlos", "publicAccountId": "abc", "userId": 1, "whatsapp": {"enabled": None}},
    "zapListingId": None,
})
(F / "ad_scam.html").write_text(ad_page(scam), encoding="utf-8")

# --- búsqueda (formato RSC de Next.js) ---
def item(lid, subj, price, pro, seller, props_, old=None, imgs=20, nb="Tarumã"):
    return {"subject": subj, "priceValue": price, "oldPrice": old, "professionalAd": pro, "listId": lid, "lastBumpAgeSecs": "0",
            "categoryName": "Apartamentos", "images": [{"original": "https://img.olx.com.br/images/x.jpg"}], "videoCount": 0,
            "location": f"Curitiba, {nb}", "properties": [{"name": n, "value": v, "label": n} for n, v in props_], "price": price,
            "isChatEnabled": True, "url": f"https://pr.olx.com.br/regiao-de-curitiba-e-paranagua/imoveis/x-{lid}", "date": 1790375990,
            "imageCount": imgs, "category": "Apartamentos", "position": 0, "isOnline": False,
            "locationDetails": {"municipality": "Curitiba", "ddd": "41", "neighbourhood": nb, "uf": "PR"}, "isFeatured": False,
            "olxPay": {"transactionalSellerName": seller}}
ads = [
    item(1538924824, "STUDIO TOTALMENTE MOBILIADO", "R$ 1.850", True, "Especiale Imóveis",
         [("condominio", "R$ 370"), ("iptu", "R$ 58"), ("size", "35m²"), ("rooms", "1"), ("bathrooms", "1"), ("re_features", "Mobiliado")]),
    {"advertisingId": "advertising-desktop-listing-native-direct"},
    item(1538219886, "Apartamento Capão da Embuia.", "R$ 1.600", False, "rodrigolopes222",
         [("condominio", "R$ 0"), ("iptu", "R$ 0"), ("size", "45m²"), ("rooms", "2"), ("bathrooms", "1"), ("garage_spaces", "1")]),
    item(1537126562, "Apartamento 3 quartos - Tarumã ", "R$ 2.990", False, "Thais",
         [("condominio", "R$ 0"), ("size", "90m²"), ("rooms", "5 ou mais")], old="R$ 3.000", imgs=3),
]
for i in range(6):
    ads.append(item(1500000000 + i, f"Apto {i}", f"R$ {1700 + i * 100}", True, "Imob", [("size", f"{40 + i}m²"), ("rooms", "1")]))
obj = {"ads": ads, "searchBoxProps": {}, "pageIndex": 1, "totalOfAds": 24, "pageTitle": "Imóveis para alugar - Tarumã, Boa Vista - PR", "pageSize": 50}
line = '1b:[["$","main",null,{"children":["$","$L25",null,' + json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + ']}]]\n'
half = len(line) // 2  # partido en dos pushes, como puede ocurrir en la página real
pushes = "".join(f"<script>self.__next_f.push({json.dumps([1, part], ensure_ascii=False)})</script>" for part in (line[:half], line[half:]))
page = ('<!DOCTYPE html><html><head></head><body><script>self.__next_f.push([0])</script>'
        '<script>self.__next_f.push([1,"0:{\\"P\\":null}\\n"])</script>' + pushes + '</body></html>')
(F / "search.html").write_text(page, encoding="utf-8")
print("fixtures ok")
