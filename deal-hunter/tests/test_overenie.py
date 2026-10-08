"""Testy hľadania na webe: overenie ponúk voči skutočnému obsahu stránky."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STRANKA_DEAL = (
    '<html><head><title>Slúchadlá Sony WH | Shop.sk</title>'
    '<meta property="og:title" content="Slúchadlá Sony WH | Shop.sk">'
    '<meta property="og:image" content="https://shop.sk/i.jpg">'
    '<meta name="description" content="Bezdrôtové slúchadlá."></head>'
    '<body><span>Pôvodne 129,90 €</span><b>Teraz 79,90 €</b></body></html>'
)

STRANKA_JSONLD = (
    '<html><head><title>Kreslo Relax | Nabytok.sk</title>'
    '<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Kreslo Relax",'
    '"offers":{"@type":"Offer","price":"89.90","priceCurrency":"EUR","availability":"https://schema.org/InStock"}}'
    '</script></head><body><del>149,00 €</del> <b>89,90 €</b></body></html>'
)


def test_prijme_deal_len_ked_ceny_potvrdi_stranka():
    from scrapers.overenie import over_navrh

    n = {"typ": "deal", "skupina": "technológie a gaming", "url": "https://shop.sk/p/1",
         "cena": 79.90, "povodna_cena": 129.90}
    c = over_navrh(n, STRANKA_DEAL)
    assert c and c.deal_price == 79.9 and c.original_price == 129.9
    assert c.title == "Slúchadlá Sony WH" and c.category_hint == "Elektronika" and c.direct_url
    assert c.discount_percent == pytest.approx(38.5, abs=0.1)
    assert over_navrh({**n, "cena": 59.90}, STRANKA_DEAL) is None
    assert over_navrh({**n, "povodna_cena": 199.0}, STRANKA_DEAL) is None


def test_zahodi_agregator_nezabezpeceny_odkaz_a_zakazany_obsah():
    from scrapers.overenie import over_navrh

    n = {"typ": "deal", "skupina": "móda", "url": "https://shop.sk/p/1", "cena": 79.90, "povodna_cena": 129.90}
    assert over_navrh({**n, "url": "http://shop.sk/p/1"}, STRANKA_DEAL) is None
    assert over_navrh({**n, "url": "https://www.heureka.sk/x"}, STRANKA_DEAL) is None
    assert over_navrh(n, STRANKA_DEAL.replace("Slúchadlá Sony WH", "Whisky 12 ročná")) is None


def test_freebie_vyzaduje_slovo_zadarmo_na_stranke():
    from scrapers.overenie import over_navrh

    n = {"typ": "freebie", "skupina": "knihy a vzdelávanie", "url": "https://kniha.sk/e"}
    ano = over_navrh(n, "<html><title>E-kniha Spánok</title><body>Stiahni si e-knihu zadarmo.</body></html>")
    assert ano and ano.zadarmo and ano.deal_price == 0 and ano.discount_percent == 100
    d = ano.to_firestore_dict()
    assert d["zadarmo"] is True and d["dealPrice"] == 0
    assert over_navrh(n, "<html><title>E-kniha</title><body>Cena 9,90 €</body></html>") is None


def test_json_a_cena_v_texte():
    from scrapers.overenie import cena_v_texte

    assert cena_v_texte("teraz 12,99 € s dph", 12.99) and cena_v_texte("len 12 €", 12.0)
    assert not cena_v_texte("cena 112,99 €", 12.99) and not cena_v_texte("od 12,990", 12.99)


def test_freebie_prejde_kontrolou_zmysluplnosti_a_ma_vlastnu_skupinu():
    import main
    from garancie import skupina_dealu
    from models import DealCandidate

    f = DealCandidate(title="Krém zadarmo", deal_price=0, url="https://x.sk/f", source="web-hunt",
                      store="X", explicit_discount_percent=100, zadarmo=True)
    assert main.is_sane(f)
    assert skupina_dealu(f) == "freebie"


def test_bez_ai_vytiahne_zlavu_zo_strukturovanych_dat():
    from scrapers.overenie import extrahuj_ponuku, over_stranku

    e = extrahuj_ponuku(STRANKA_JSONLD)
    assert e["cena"] == 89.9 and e["povodna"] == 149.0
    c = over_stranku("https://nabytok.sk/kreslo", STRANKA_JSONLD, "deal", "domácnosť a záhrada")
    assert c and c.deal_price == 89.9 and c.original_price == 149.0 and c.category_hint == "Dom & Záhrada"
    bez_zlavy = STRANKA_JSONLD.replace("<del>149,00 €</del>", "")
    assert over_stranku("https://nabytok.sk/k", bez_zlavy, "deal", "móda") is None
    assert over_stranku("https://nabytok.sk/k", STRANKA_JSONLD.replace("InStock", "OutOfStock"), "deal", "móda") is None


def test_bez_ai_freebie_nesmie_mat_cenu():
    from scrapers.overenie import over_stranku

    zdarma = "<html><title>Vzorka krému | Kozmetika.sk</title><body>Vzorka zadarmo k objednávke.</body></html>"
    assert over_stranku("https://kozmetika.sk/vzorka", zdarma, "freebie", "kozmetika a starostlivosť").zadarmo
    platena = STRANKA_JSONLD + " zadarmo"
    assert over_stranku("https://nabytok.sk/kreslo", platena, "freebie", "móda") is None


def test_sitemap_parsuje_stranky_aj_index_a_vybera_vzorku():
    import gzip
    import random
    from scrapers.sitemap_hunt import parsuj_sitemapu, vyber_vzorku

    xml = ('<?xml version="1.0"?><urlset><url><loc>https://s.sk/p/1</loc></url>'
           '<url><loc>https://s.sk/p/2?a=1&amp;b=2</loc></url></urlset>').encode()
    stranky, dalsie = parsuj_sitemapu(xml)
    assert stranky == ["https://s.sk/p/1", "https://s.sk/p/2?a=1&b=2"] and dalsie == []
    assert parsuj_sitemapu(gzip.compress(xml))[0] == stranky
    idx = b'<sitemapindex><sitemap><loc>https://s.sk/sm1.xml</loc></sitemap></sitemapindex>'
    assert parsuj_sitemapu(idx) == ([], ["https://s.sk/sm1.xml"])
    v = vyber_vzorku([f"u{i}" for i in range(100)], 10, random.Random(1))
    assert len(v) == len(set(v)) == 10
    assert len(vyber_vzorku(["a", "b"], 10)) == 2


def test_obchody_pre_sitemap_z_admina_nahradia_predvolene_a_preskocia_zle():
    import config

    povodne = list(config.SITEMAP_OBCHODY)
    try:
        n = config.pouzi_sitemap({"obchody": [
            {"domena": "www.Shop.sk", "sitemapy": ["https://shop.sk/sm.xml"], "strana": 25},
            {"domena": "vypnuty.sk", "sitemapy": ["https://vypnuty.sk/sm.xml"], "zap": False},
            {"domena": "bez-sitemapy.sk", "sitemapy": []},
            {"domena": "http.sk", "sitemapy": ["http://http.sk/sm.xml"]},
        ]})
        assert n == 1
        assert config.SITEMAP_OBCHODY == [{"domena": "shop.sk", "sitemapy": ["https://shop.sk/sm.xml"], "strana": 25}]
        assert config.pouzi_sitemap({}) == 0 and len(config.SITEMAP_OBCHODY) == 1   # bez dokumentu sa nič nemení
    finally:
        config.SITEMAP_OBCHODY = povodne


def test_ehub_zhrnutie_kampani_transakcii_a_preklikov():
    import ehub

    k = [
        {"id": "a", "name": "AliExpress", "country": "other", "commissionGroups": [
            {"status": "approved", "commissions": [{"commissionType": "PPS", "valueType": "%", "value": 2.3},
                                                    {"commissionType": "PPS", "valueType": "%", "value": 7.0}]}]},
        {"id": "b", "name": "Alza.sk", "country": "SK", "commissionGroups": [{"status": "declined", "commissions": []}]},
        {"id": "c", "name": "Iný", "country": "SK", "commissionGroups": [{"status": "approval_required", "commissions": []}]},
    ]
    zh = ehub.zhrn_kampane(k)
    assert [x["stav"] for x in zh] == ["approved", "available", "declined"]
    assert zh[0]["provizia"] == 7.0 and zh[0]["jednotka"] == "%"
    nazvy = {x["id"]: x["nazov"] for x in zh}

    t = [
        {"dateInserted": "2026-09-01T10:00:00+02:00", "campaignId": "a", "commission": 4.0, "amount": 80.0,
         "status": "approved", "payoutStatus": "unpaid", "orderId": "1"},
        {"dateInserted": "2026-09-05T10:00:00+02:00", "campaignId": "a", "commission": 1.0, "amount": 20.0,
         "status": "approved", "payoutStatus": "paid", "orderId": "2"},
        {"dateInserted": "2026-10-01T10:00:00+02:00", "campaignId": "a", "commission": 9.0, "amount": 90.0,
         "status": "declined", "payoutStatus": "unpaid", "orderId": "3"},
    ]
    z = ehub.zhrn_transakcie(t, nazvy, 25.0)
    # Sumy v CZK, kurz 25 Kč = 1 €: 5 Kč provízie = 0,20 €.
    assert z["stavy"]["approved"]["proviziaCzk"] == 5.0 and z["stavy"]["approved"]["provizia"] == 0.2
    assert z["stavy"]["declined"]["pocet"] == 1
    assert z["vyplateneCzk"] == 1.0 and z["schvaleneNevyplateneCzk"] == 4.0 and z["vyplatene"] == 0.04
    assert z["mesiace"] == {"2026-09": {"eur": 0.2, "czk": 5.0}}   # zamietnuté sa do mesiacov nepočítajú
    assert z["posledne"][0]["suma"] == 3.6 and z["posledne"][0]["sumaCzk"] == 90.0
    assert z["posledne"][0]["objednavka"] == "3" and z["posledne"][0]["kampan"] == "AliExpress"

    from datetime import datetime, timezone
    dnes = datetime.now(timezone.utc).date().isoformat()
    kl = ehub.zhrn_kliky([{"campaignId": "a", "dateTime": dnes + "T10:00:00"},
                          {"campaignId": "a", "dateTime": "2020-01-01T10:00:00"}], nazvy)
    assert kl["spolu"] == 1 and kl["poKampani"][0]["nazov"] == "AliExpress"


def test_ehub_kurz_z_ecb_sa_precita(monkeypatch):
    import ehub

    class R:
        text = ("<gesmes:Envelope><Cube><Cube time='2026-10-08'><Cube currency='USD' rate='1.09'/>"
                "<Cube currency='CZK' rate='24.31'/></Cube></Cube></gesmes:Envelope>")

        def raise_for_status(self):
            pass

    monkeypatch.setattr(ehub.requests, "get", lambda *a, **k: R())
    assert ehub.kurz_czk() == (24.31, "2026-10-08")


def test_import_z_odkazu_najde_fotku_aj_ked_je_relativna_alebo_len_v_obrazku():
    import admin_ulohy as a

    # og:image bez domény
    h1 = '<html><head><title>X</title><meta property="og:image" content="/media/p/1.jpg"></head><body></body></html>'
    assert a._rozober(h1, "https://shop.sk/produkt/1")["imageUrl"] == "https://shop.sk/media/p/1.jpg"
    # JSON-LD image ako odkaz na iný objekt (@id)
    h2 = ('<script type="application/ld+json">{"@graph":[{"@type":"Product","name":"P","image":{"@id":"#f"},'
          '"offers":{"price":"9.90"}},{"@type":"ImageObject","@id":"#f","url":"https://cdn.shop.sk/f.webp"}]}</script>')
    assert a._rozober(h2, "https://shop.sk/p")["imageUrl"] == "https://cdn.shop.sk/f.webp"
    # žiadne meta - berie sa hlavný obrázok produktu (leniváci data-src), logo sa preskočí
    h3 = ('<html><body><img class="logo" src="/logo.png">'
          '<img class="product-gallery__image" data-src="//cdn.shop.sk/big.jpg" src="data:image/gif;base64,xx"></body></html>')
    assert a._rozober(h3, "https://shop.sk/p")["imageUrl"] == "https://cdn.shop.sk/big.jpg"
    assert a._rozober("<html><body>nič</body></html>", "https://shop.sk/p")["imageUrl"] is None


def test_import_z_odkazu_nacita_aj_povodnu_cenu():
    import admin_ulohy as a

    h = ('<html><head><title>Kreslo | Shop</title>'
         '<script type="application/ld+json">{"@type":"Product","name":"Kreslo","offers":{"@type":"Offer","price":"89.90",'
         '"priceCurrency":"EUR","availability":"https://schema.org/InStock"}}</script></head>'
         '<body><del>149,00 €</del> <b>89,90 €</b></body></html>')
    r = a._rozober(h, "https://shop.sk/kreslo")
    assert r["dealPrice"] == 89.9 and r["originalPrice"] == 149.0 and r["title"] == "Kreslo"
    bez = h.replace("<del>149,00 €</del>", "")
    assert a._rozober(bez, "https://shop.sk/kreslo")["originalPrice"] is None
