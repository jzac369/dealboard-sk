"""
Offline testy parsovania.

Bežia proti uloženému HTML v tests/fixtures/, takže nepotrebujú internet
ani Firebase a nezaťažujú cudzí server.

Spustenie:  python -m pytest tests/ -v
"""

import sys
from pathlib import Path

import pytest

# Aby sa dali importovať moduly z koreňa projektu.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import DealCandidate, guess_category, parse_price  # noqa: E402
from scrapers.zlacnene import ZlacneneScraper  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def zlacnene_html() -> str:
    return (FIXTURES / "zlacnene_akciovy_tovar.html").read_text(encoding="utf-8")


# ── ceny ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1 399,50 EUR", 1399.50),   # medzera ako oddeľovač tisícov
        ("1.399,50", 1399.50),       # bodka ako oddeľovač tisícov
        ("23,12", 23.12),            # slovenská desatinná čiarka
        ("1399.50", 1399.50),        # anglický formát
        ("2,99 - 3,29", 2.99),       # rozsah -> nižšia cena
        ("\xa04,50\xa0", 4.50),      # nezalomiteľné medzery
        ("nie je cena", None),
        ("", None),
        (None, None),
        ("0", None),                 # nulová cena nie je platná cena
    ],
)
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


# ── kategórie ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "title, expected",
    [
        ("Bravčové karé bez kosti 1 kg", "Jedlo & Nápoje"),
        ("Apple AirPods Pro 2 slúchadlá", "Elektronika"),
        ("Sedacia súprava rohová", "Dom & Záhrada"),
        ("Pánske tenisky Nike", "Móda"),
        ("Horský bicykel 29\"", "Šport"),
        ("LEGO Technic 42154", "Hračky"),
        ("Dovolenka Chorvátsko 7 nocí", "Cestovanie"),
        ("Úplne neznáma vec xyz", "Iné"),
    ],
)
def test_guess_category(title, expected):
    assert guess_category(title) == expected


def test_category_hint_wins_over_guess():
    # Ak zdroj kategóriu pozná, veríme jemu, nie hádaniu z názvu.
    assert guess_category("Bravčové karé", hint="Elektronika") == "Elektronika"
    # Neplatnú kategóriu ignorujeme a hádame ďalej.
    assert guess_category("Bravčové karé", hint="Vymyslená") == "Jedlo & Nápoje"


# ── výpočet zľavy ─────────────────────────────────────────────────────

def test_discount_from_prices():
    deal = DealCandidate(
        title="Test", deal_price=50.0, original_price=100.0,
        url="https://x.sk", source="test",
    )
    assert deal.discount_percent == 50.0
    assert deal.effective_original_price == 100.0


def test_explicit_discount_wins_and_backfills_original_price():
    # Zdroj udáva -40 %, pôvodnú cenu nie -> dopočítame ju.
    deal = DealCandidate(
        title="Test", deal_price=2.99, explicit_discount_percent=40,
        url="https://x.sk", source="test",
    )
    assert deal.discount_percent == 40
    assert deal.effective_original_price == pytest.approx(4.98, abs=0.01)


def test_no_discount_when_original_price_is_lower():
    # Chybné dáta (pôvodná cena nižšia než akciová) nesmú vyrobiť zápornú zľavu.
    deal = DealCandidate(
        title="Test", deal_price=100.0, original_price=50.0,
        url="https://x.sk", source="test",
    )
    assert deal.discount_percent == 0.0


def test_dedupe_key_ignores_diacritics_and_case():
    common = dict(deal_price=1.0, url="https://x.sk", source="test", store="BILLA")
    a = DealCandidate(title="Bravčové karé", **common)
    b = DealCandidate(title="bravcove kare", **common)
    assert a.dedupe_key == b.dedupe_key


# ── mapovanie na schému stránky ───────────────────────────────────────

def test_firestore_dict_matches_site_schema():
    """
    Toto je najdôležitejší test v projekte. Ak sa názov poľa rozíde so
    schémou henkukaj.sk, deal sa zapíše, ale na stránke bude prázdna karta.
    """
    deal = DealCandidate(
        title="Lindt Excellence 100 g",
        deal_price=2.99,
        explicit_discount_percent=40,
        url="https://www.zlacnene.sk/akcia/lindt/",
        source="zlacnene.sk",
        store="BILLA",
        valid_until="22.9.2026",
    )
    doc = deal.to_firestore_dict()

    required = {
        "title", "store", "category", "originalPrice", "dealPrice",
        "discountPercent", "currency", "url", "imageUrl", "description",
        "votes", "comments", "status", "expired",
    }
    assert required.issubset(doc.keys())

    assert doc["status"] == "pending"      # musí čakať na schválenie
    assert doc["expired"] is False
    assert doc["votes"] == 0
    assert doc["dealPrice"] == 2.99
    assert doc["currency"] == "€"
    assert doc["category"] in {
        "Elektronika", "Dom & Záhrada", "Móda", "Hračky",
        "Šport", "Jedlo & Nápoje", "Cestovanie", "Iné",
    }
    assert "22.9.2026" in doc["description"]
    # timestamp dopĺňa až firestore_client cez SERVER_TIMESTAMP
    assert "timestamp" not in doc


# ── scraper zlacnene.sk ───────────────────────────────────────────────

def test_zlacnene_parses_products(zlacnene_html):
    candidates = ZlacneneScraper().parse_listing(zlacnene_html)
    # Listing má 20 produktov na stranu, z toho časť býva bez uvedenej zľavy
    # (tie zahadzujeme). Ak ich zrazu je výrazne menej, zmenila sa štruktúra
    # stránky a parser treba opraviť podľa návodu v README.
    assert 10 <= len(candidates) <= 20


def test_zlacnene_skips_items_without_discount(zlacnene_html):
    # Položka bez uvedenej zľavy by na stránke bola karta s "-0 %".
    for c in ZlacneneScraper().parse_listing(zlacnene_html):
        assert c.explicit_discount_percent is not None


def test_zlacnene_extracts_complete_data(zlacnene_html):
    candidates = ZlacneneScraper().parse_listing(zlacnene_html)

    for c in candidates:
        assert c.title.strip()
        assert c.deal_price > 0
        assert c.url.startswith("https://www.zlacnene.sk/")
        assert c.store, f"chýba obchod pri '{c.title}'"
        assert c.image_url and c.image_url.startswith("http")
        assert 0 < c.discount_percent < 100


def test_zlacnene_picks_cheapest_seller(zlacnene_html):
    candidates = ZlacneneScraper().parse_listing(zlacnene_html)
    by_title = {c.title: c for c in candidates}

    # Lindt je v letáku viacerých predajcov; berieme najnižšiu cenu (2,99 v BILLA).
    lindt = next((c for t, c in by_title.items() if "Lindt" in t), None)
    assert lindt is not None
    assert lindt.deal_price == 2.99
    assert lindt.store == "BILLA"


def test_zlacnene_survives_broken_html():
    # Nezmyselný vstup nesmie vyhodiť výnimku, len vrátiť prázdny zoznam.
    assert ZlacneneScraper().parse_listing("<html><body>nič</body></html>") == []
    assert ZlacneneScraper().parse_listing("") == []


# ── affiliate feedy ───────────────────────────────────────────────────

GOOGLE_FEED = """<?xml version="1.0"?>
<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">
  <channel>
    <item>
      <g:title>Notebook Lenovo IdeaPad</g:title>
      <g:link>https://partner.sk/p/1?a_aid=henkukaj</g:link>
      <g:price>899.00 EUR</g:price>
      <g:sale_price>599.00 EUR</g:sale_price>
      <g:image_link>https://partner.sk/img/1.jpg</g:image_link>
      <g:brand>Lenovo</g:brand>
      <g:description>Notebook s 16 GB RAM</g:description>
    </item>
    <item>
      <g:title>Bez akciovej ceny</g:title>
      <g:link>https://partner.sk/p/2</g:link>
      <g:price>50.00 EUR</g:price>
    </item>
    <item>
      <g:title>Akciova cena vyssia nez bezna</g:title>
      <g:link>https://partner.sk/p/3</g:link>
      <g:price>10.00 EUR</g:price>
      <g:sale_price>20.00 EUR</g:sale_price>
    </item>
  </channel>
</rss>"""

HEUREKA_FEED = """<?xml version="1.0" encoding="utf-8"?>
<SHOP>
  <SHOPITEM>
    <PRODUCTNAME>Kavovar DeLonghi</PRODUCTNAME>
    <URL>https://partner.sk/kavovar</URL>
    <PRICE_VAT>199.00</PRICE_VAT>
    <PRICE_BEFORE_DISCOUNT>349.00</PRICE_BEFORE_DISCOUNT>
    <IMGURL>https://partner.sk/img/k.jpg</IMGURL>
    <MANUFACTURER>DeLonghi</MANUFACTURER>
  </SHOPITEM>
  <SHOPITEM>
    <PRODUCTNAME>Bez povodnej ceny</PRODUCTNAME>
    <URL>https://partner.sk/x</URL>
    <PRICE_VAT>99.00</PRICE_VAT>
  </SHOPITEM>
</SHOP>"""


def test_google_feed_parsing():
    from scrapers.feeds import FeedsScraper

    candidates = FeedsScraper().parse_feed(GOOGLE_FEED)
    # Položka bez akciovej ceny a položka s nezmyselnou cenou sa zahadzujú.
    assert len(candidates) == 1

    deal = candidates[0]
    assert deal.title == "Notebook Lenovo IdeaPad"
    assert deal.deal_price == 599.0
    assert deal.original_price == 899.0
    assert deal.discount_percent == pytest.approx(33.4, abs=0.1)
    # Affiliate parameter v odkaze musí prežiť nedotknutý.
    assert "a_aid=henkukaj" in deal.url


def test_heureka_feed_parsing():
    from scrapers.feeds import FeedsScraper

    candidates = FeedsScraper().parse_feed(HEUREKA_FEED)
    assert len(candidates) == 1
    assert candidates[0].title == "Kavovar DeLonghi"
    assert candidates[0].deal_price == 199.0
    assert candidates[0].store == "DeLonghi"


def test_broken_feed_returns_empty_not_crash():
    from scrapers.feeds import FeedsScraper

    assert FeedsScraper().parse_feed("toto nie je XML") == []
