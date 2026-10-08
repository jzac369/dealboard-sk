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
    from scrapers.web_hunt import over_navrh

    n = {"typ": "deal", "skupina": "technológie a gaming", "url": "https://shop.sk/p/1",
         "cena": 79.90, "povodna_cena": 129.90}
    c = over_navrh(n, STRANKA_DEAL)
    assert c and c.deal_price == 79.9 and c.original_price == 129.9
    assert c.title == "Slúchadlá Sony WH" and c.category_hint == "Elektronika" and c.direct_url
    assert c.discount_percent == pytest.approx(38.5, abs=0.1)
    assert over_navrh({**n, "cena": 59.90}, STRANKA_DEAL) is None
    assert over_navrh({**n, "povodna_cena": 199.0}, STRANKA_DEAL) is None


def test_zahodi_agregator_nezabezpeceny_odkaz_a_zakazany_obsah():
    from scrapers.web_hunt import over_navrh

    n = {"typ": "deal", "skupina": "móda", "url": "https://shop.sk/p/1", "cena": 79.90, "povodna_cena": 129.90}
    assert over_navrh({**n, "url": "http://shop.sk/p/1"}, STRANKA_DEAL) is None
    assert over_navrh({**n, "url": "https://www.heureka.sk/x"}, STRANKA_DEAL) is None
    assert over_navrh(n, STRANKA_DEAL.replace("Slúchadlá Sony WH", "Whisky 12 ročná")) is None


def test_freebie_vyzaduje_slovo_zadarmo_na_stranke():
    from scrapers.web_hunt import over_navrh

    n = {"typ": "freebie", "skupina": "knihy a vzdelávanie", "url": "https://kniha.sk/e"}
    ano = over_navrh(n, "<html><title>E-kniha Spánok</title><body>Stiahni si e-knihu zadarmo.</body></html>")
    assert ano and ano.zadarmo and ano.deal_price == 0 and ano.discount_percent == 100
    d = ano.to_firestore_dict()
    assert d["zadarmo"] is True and d["dealPrice"] == 0
    assert over_navrh(n, "<html><title>E-kniha</title><body>Cena 9,90 €</body></html>") is None


def test_json_a_cena_v_texte():
    from scrapers.web_hunt import cena_v_texte, vytiahni_json

    assert vytiahni_json('Tu je výsledok: [{"url": "https://a.sk"}] hotovo')[0]["url"] == "https://a.sk"
    assert vytiahni_json("nič nenašiel") == [] and vytiahni_json("[nie json]") == []
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
    from scrapers.web_hunt import extrahuj_ponuku, over_stranku

    e = extrahuj_ponuku(STRANKA_JSONLD)
    assert e["cena"] == 89.9 and e["povodna"] == 149.0
    c = over_stranku("https://nabytok.sk/kreslo", STRANKA_JSONLD, "deal", "domácnosť a záhrada")
    assert c and c.deal_price == 89.9 and c.original_price == 149.0 and c.category_hint == "Dom & Záhrada"
    bez_zlavy = STRANKA_JSONLD.replace("<del>149,00 €</del>", "")
    assert over_stranku("https://nabytok.sk/k", bez_zlavy, "deal", "móda") is None
    assert over_stranku("https://nabytok.sk/k", STRANKA_JSONLD.replace("InStock", "OutOfStock"), "deal", "móda") is None


def test_bez_ai_freebie_nesmie_mat_cenu():
    from scrapers.web_hunt import over_stranku

    zdarma = "<html><title>Vzorka krému | Kozmetika.sk</title><body>Vzorka zadarmo k objednávke.</body></html>"
    assert over_stranku("https://kozmetika.sk/vzorka", zdarma, "freebie", "kozmetika a starostlivosť").zadarmo
    platena = STRANKA_JSONLD + " zadarmo"
    assert over_stranku("https://nabytok.sk/kreslo", platena, "freebie", "móda") is None
