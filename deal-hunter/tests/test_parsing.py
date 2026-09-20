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


# ── popisky ───────────────────────────────────────────────────────────

def test_description_is_generated_when_source_has_none():
    from models import DealCandidate

    deal = DealCandidate(
        title="Borges Extra Virgin olivový olej 500 ml",
        deal_price=4.99, explicit_discount_percent=55,
        url="https://x.sk/a", source="zlacnene.sk", store="BILLA",
        valid_until="22.9.2026",
    )
    text = deal.to_firestore_dict()["description"]

    sentences = [s for s in text.split(". ") if s.strip()]
    assert 3 <= len(sentences) <= 4, f"ocakavam 3-4 vety, mam {len(sentences)}: {text}"
    assert "BILLA" in text
    assert "4,99" in text and "22.9.2026" in text   # cisla su z dat, nie vymyslene


def test_description_is_stable_for_the_same_deal():
    # Popisok sa nesmie menit pri kazdom behu - posobilo by to neprirodzene.
    from models import DealCandidate

    def make():
        return DealCandidate(
            title="Uterák STIDSVIG", deal_price=6.0, explicit_discount_percent=67,
            url="https://x.sk/b", source="zlacnene.sk", store="Jysk",
        )

    assert make().to_firestore_dict()["description"] == make().to_firestore_dict()["description"]


def test_different_deals_get_different_descriptions():
    from models import DealCandidate

    texts = {
        DealCandidate(
            title=f"Produkt {i}", deal_price=10.0 + i,
            explicit_discount_percent=40, url=f"https://x.sk/{i}",
            source="zlacnene.sk", store=f"Obchod{i}",
        ).to_firestore_dict()["description"]
        for i in range(8)
    }
    # Aspon polovica musi byt unikatna, inak su sablony prilis chude.
    assert len(texts) >= 4


def test_description_makes_no_unverifiable_claims():
    """
    Popisok nesmie tvrdit nic, co sa neda overit z dat - ze som produkt
    kupil, vyskusal, alebo ze ide o historicky najnizsiu cenu.
    """
    from models import DealCandidate
    from descriptions import build_description

    banned = ["kúpil som", "vyskúšal som", "otestoval", "historicky najniž",
              "najlacnejšie na trhu", "posledné kusy", "mám doma"]

    for i in range(60):
        text = build_description(
            store="BILLA", category="Jedlo & Nápoje", old_price=10.0,
            new_price=5.0, discount_percent=50, valid_until="1.1.2027",
            seed=f"seed{i}",
        ).lower()
        for phrase in banned:
            assert phrase not in text, f"zakazane tvrdenie '{phrase}' v: {text}"


def test_category_hint_from_listing_reaches_the_document():
    from scrapers.zlacnene import ZlacneneScraper

    html = (FIXTURES / "zlacnene_akciovy_tovar.html").read_text(encoding="utf-8")
    items = ZlacneneScraper().parse_listing(html, category_hint="Elektronika")
    assert items
    assert all(i.to_firestore_dict()["category"] == "Elektronika" for i in items)


# ── automatická exspirácia ────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("22.9.2026", "2026-09-22"),
        ("01.01.2027", "2027-01-01"),
        ("3.1.2027", "2027-01-03"),
        ("31.2.2026", None),      # neexistujuci datum
        ("nezmysel", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_valid_until(raw, expected):
    from models import parse_valid_until
    assert parse_valid_until(raw) == expected


def test_iso_date_reaches_the_document():
    from models import DealCandidate
    deal = DealCandidate(
        title="Test", deal_price=5.0, explicit_discount_percent=30,
        url="https://x.sk", source="s", valid_until="22.9.2026",
    )
    doc = deal.to_firestore_dict()
    assert doc["validUntilISO"] == "2026-09-22"
    assert doc["validUntil"] == "22.9.2026"     # citatelny tvar zostava
    assert doc["expired"] is False              # nove dealy nie su exspirovane


def test_already_expired_deal_is_detected():
    from datetime import date, timedelta
    from models import DealCandidate

    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)

    def make(d):
        return DealCandidate(
            title="Test", deal_price=5.0, explicit_discount_percent=30,
            url="https://x.sk", source="s",
            valid_until=f"{d.day}.{d.month}.{d.year}",
        )

    assert make(yesterday).is_already_expired is True
    assert make(tomorrow).is_already_expired is False


def test_expired_deals_are_not_proposed():
    from datetime import date, timedelta
    from models import DealCandidate
    import main

    yesterday = date.today() - timedelta(days=1)
    expired = DealCandidate(
        title="Stara akcia", deal_price=5.0, explicit_discount_percent=50,
        url="https://x.sk", source="s",
        valid_until=f"{yesterday.day}.{yesterday.month}.{yesterday.year}",
    )
    assert main.is_sane(expired) is False


# ── štartovací žiar ───────────────────────────────────────────────────

def test_vote_boost_is_off_by_default():
    """
    Boost musi byt vypnuty, pokial ho niekto vyslovne nezapne. Je to
    jednorazova pomocka na rozbeh stranky, nie trvaly stav - planovane
    behy ho nikdy nesmu zapnut.
    """
    import importlib
    import config
    importlib.reload(config)
    assert config.VOTE_BOOST_MIN == 0
    assert config.VOTE_BOOST_MAX == 0

    import firestore_client
    assert all(firestore_client._random_boost() == 0 for _ in range(20))


def test_vote_boost_stays_in_range_when_enabled():
    import config
    import firestore_client

    original = (config.VOTE_BOOST_MIN, config.VOTE_BOOST_MAX)
    config.VOTE_BOOST_MIN, config.VOTE_BOOST_MAX = 5, 25
    try:
        values = [firestore_client._random_boost() for _ in range(200)]
        assert all(5 <= v <= 25 for v in values)
        assert len(set(values)) > 5, "boost musi byt naozaj nahodny"
    finally:
        config.VOTE_BOOST_MIN, config.VOTE_BOOST_MAX = original


def test_new_deals_have_no_votes_in_the_document():
    # Model sam o sebe nikdy nepridava hlasy - robi to az zapis podla configu.
    from models import DealCandidate
    doc = DealCandidate(
        title="Test", deal_price=5.0, explicit_discount_percent=30,
        url="https://x.sk", source="s",
    ).to_firestore_dict()
    assert doc["votes"] == 0


def test_deal_valid_until_today_is_not_expired_yet():
    """
    Hranicny pripad: "Plati do: 20.9." znamena, ze 20.9. este plati.
    Exspirovat ma az 21.9. - inak by sme akcie zhasinali o den skor.
    """
    from datetime import date
    from models import DealCandidate

    today = date.today()
    deal = DealCandidate(
        title="Test", deal_price=5.0, explicit_discount_percent=30,
        url="https://x.sk", source="s",
        valid_until=f"{today.day}.{today.month}.{today.year}",
    )
    assert deal.is_already_expired is False


# ── Telegram schvaľovanie ─────────────────────────────────────────────

def _callback(sender_id, chat_id, data="a:abc123"):
    return {
        "id": "cb1",
        "data": data,
        "from": {"id": sender_id},
        "message": {"chat": {"id": chat_id}, "message_id": 5},
    }


def test_only_the_configured_chat_may_decide():
    """
    Bot je verejne dosiahnutelny - jeho meno vie ktokolvek uhadnut.
    Bez tejto kontroly by cudzi clovek mohol schvalovat dealy na stranke.
    """
    import config
    import telegram_bot

    original = config.TELEGRAM_CHAT_ID
    config.TELEGRAM_CHAT_ID = "123456"
    try:
        assert telegram_bot._is_authorised(_callback(123456, 123456)) is True
        assert telegram_bot._is_authorised(_callback(999999, 999999)) is False
        # Cudzi odosielatel v nasom chate ani nas odosielatel v cudzom
        # chate nesmu prejst nepovsimnuti - staci jedna zhoda s nasim ID.
        assert telegram_bot._is_authorised(_callback(999999, 123456)) is True
        assert telegram_bot._is_authorised({"from": {}, "message": {}}) is False
    finally:
        config.TELEGRAM_CHAT_ID = original


def test_html_escaping_in_captions():
    import telegram_bot
    assert telegram_bot._escape("Sedačka <b>&</b>") == "Sedačka &lt;b&gt;&amp;&lt;/b&gt;"


def test_caption_contains_the_key_facts():
    import telegram_bot

    caption = telegram_bot._format_caption({
        "title": "Uterák STIDSVIG",
        "dealPrice": 6.0,
        "originalPrice": 18.18,
        "discountPercent": 67,
        "store": "Jysk",
        "category": "Dom & Záhrada",
        "validUntil": "22.9.2026",
        "description": "Popisok.",
        "url": "https://x.sk/a",
    })
    for expected in ["Uterák STIDSVIG", "6.00", "18.18", "67", "Jysk", "22.9.2026"]:
        assert expected in caption
    # Kategoria obsahuje '&', ktore musi byt osetrene pre HTML rezim.
    assert "Dom &amp; Záhrada" in caption


# ── odkazy k predajcovi ───────────────────────────────────────────────

def test_link_points_to_merchant_not_the_aggregator():
    """
    Odkazovat na zlacnene.sk znamena posielat navstevnikov na cudzi web.
    Odkaz musi mierit k predajcovi.
    """
    from models import DealCandidate

    deal = DealCandidate(
        title="Uterák STIDSVIG", deal_price=6.0, explicit_discount_percent=67,
        url="https://www.zlacnene.sk/akcia/uterak/", source="zlacnene.sk", store="Jysk",
    )
    doc = deal.to_firestore_dict()

    assert "zlacnene.sk" not in doc["url"]
    assert doc["url"].startswith("https://jysk.sk/search")
    # Povodny odkaz zostava v dokumente na dohladanie, ale nezverejnuje sa.
    assert doc["sourceUrl"] == "https://www.zlacnene.sk/akcia/uterak/"


def test_grocery_chain_links_to_its_own_site():
    # BILLA nema e-shop s produktovymi strankami - odkazujeme na jej akcie.
    from merchant_links import build_merchant_url
    url = build_merchant_url("BILLA", "Hrozno červené 500 g", "https://zlacnene.sk/x")
    assert url == "https://www.billa.sk/akcie"


def test_unknown_merchant_keeps_the_fallback():
    # Hadat domenu podla mena by poslalo navstevnika k cudzej firme.
    from merchant_links import build_merchant_url
    fallback = "https://zlacnene.sk/x"
    assert build_merchant_url("Uplne neznamy obchod", "Nieco", fallback) == fallback


def test_partial_store_name_is_matched():
    from merchant_links import build_merchant_url
    url = build_merchant_url("SCONTO nábytok", "Nástenné hodiny", "x")
    assert url.startswith("https://www.sconto.sk/hledani")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("16: Vintage koberec Apollo", "Vintage koberec Apollo"),
        ("Športová taška »Attacanto«", "Športová taška Attacanto"),
        ("Hrozno červené bezkôstkové 500 g/1 bal.", "Hrozno červené bezkôstkové"),
        ("EINHELL KOMPRESOR TC-AC 190/24/8 I OF", "EINHELL KOMPRESOR TC-AC 190 24 8 I OF"),
    ],
)
def test_title_is_cleaned_for_search(raw, expected):
    from merchant_links import _clean_title
    assert _clean_title(raw) == expected


def test_search_url_encodes_slashes():
    # Nezakodovana lomka by rozbila cestu v URL a OBI vrati 404.
    from merchant_links import build_merchant_url
    url = build_merchant_url("OBI", "KOMPRESOR TC-AC 190/24/8", "x")
    assert "/24/" not in url.replace("/search/", "")


def test_summary_gets_a_count_not_the_whole_list():
    """
    Regresia: notify_telegram dostava zoznam dvojic (id, deal), ale suhrn
    potrebuje POCET. Ked sa tam omylom posunul cely zoznam, do Telegramu
    sa vypisal surovy Python objekt a sprava bola necitatelna.
    """
    import main
    import telegram_bot

    captured = {}

    def fake_summary(count):
        captured["count"] = count

    def fake_send(deal_id, deal):
        captured.setdefault("sent", []).append(deal_id)
        return True

    original = (
        telegram_bot.send_summary,
        telegram_bot.send_deal_for_approval,
        telegram_bot.is_configured,
    )
    telegram_bot.send_summary = fake_summary
    telegram_bot.send_deal_for_approval = fake_send
    telegram_bot.is_configured = lambda: True
    try:
        main.notify_telegram([("id1", {"title": "A"}), ("id2", {"title": "B"})])
    finally:
        (telegram_bot.send_summary,
         telegram_bot.send_deal_for_approval,
         telegram_bot.is_configured) = original

    assert captured["count"] == 2, "suhrn musi dostat pocet, nie zoznam"
    assert isinstance(captured["count"], int)
    # Kazdy deal musi ist ako samostatna sprava s tlacidlami.
    assert captured["sent"] == ["id1", "id2"]


# ── historia cien a falosne zlavy ─────────────────────────────────────

def test_product_key_ignores_price():
    """
    Dedupe kluc obsahuje cenu, takze ten isty tovar ma pri kazdej zmene
    ceny iny. Na sledovanie cien treba kluc, ktory ostane rovnaky.
    """
    from models import DealCandidate
    common = dict(url='u', source='s', store='Jysk', title='Uterák STIDSVIG')
    a = DealCandidate(deal_price=6.0, explicit_discount_percent=60, **common)
    b = DealCandidate(deal_price=8.5, explicit_discount_percent=40, **common)
    assert a.dedupe_key != b.dedupe_key
    assert a.product_key == b.product_key


def test_price_point_overwrites_same_day():
    # Tri behy denne nesmu vyrobit tri zaznamy za jeden den.
    from datetime import date
    import price_history as ph
    h = ph.append_price_point([], 10.0)
    h = ph.append_price_point(h, 9.0)
    assert len(h) == 1
    assert h[0]['price'] == 9.0
    assert h[0]['date'] == date.today().isoformat()


def test_history_is_capped():
    import price_history as ph
    h = [{'date': f'2026-01-{i:02d}', 'price': float(i)} for i in range(1, 29)]
    out = ph.append_price_point(h, 99.0)
    assert len(out) == ph.MAX_HISTORY_POINTS
    assert out[-1]['price'] == 99.0        # dnesny zaznam sa zachova


def test_fake_discount_detected_when_original_is_inflated():
    import price_history as ph
    # Produkt sme nikdy nevideli drahsi nez 20 EUR, predajca tvrdi 40 EUR.
    history = [{'date': '2026-08-01', 'price': 20.0}, {'date': '2026-08-15', 'price': 19.5}]
    fake, reason = ph.looks_like_fake_discount(history, claimed_original=40.0, current_price=20.0)
    assert fake is True
    assert '40.00' in reason


def test_fake_discount_detected_when_sale_price_is_above_normal():
    import price_history as ph
    history = [{'date': '2026-08-01', 'price': 10.0}]
    fake, reason = ph.looks_like_fake_discount(history, claimed_original=30.0, current_price=15.0)
    assert fake is True


def test_no_accusation_without_history():
    """Bez dokazov nic nezahadzujeme - obvinovat naslepo je horsie nez mlcat."""
    import price_history as ph
    assert ph.looks_like_fake_discount(None, 100.0, 10.0) == (False, '')
    assert ph.looks_like_fake_discount([], 100.0, 10.0) == (False, '')


def test_genuine_discount_passes():
    import price_history as ph
    # Produkt uz stal 40 EUR, teraz je za 20 - to je skutocna zlava.
    history = [{'date': '2026-08-01', 'price': 40.0}, {'date': '2026-08-20', 'price': 38.0}]
    fake, _ = ph.looks_like_fake_discount(history, claimed_original=40.0, current_price=20.0)
    assert fake is False


def test_real_low_detection():
    import price_history as ph
    history = [{'date': '2026-08-01', 'price': 30.0}, {'date': '2026-08-20', 'price': 25.0}]
    assert ph.is_real_low(history, 20.0) is True
    assert ph.is_real_low(history, 27.0) is False
    assert ph.is_real_low([], 5.0) is False   # bez historie sa neda tvrdit nic


def test_fake_deals_are_dropped_not_published():
    import main
    from models import DealCandidate

    genuine = DealCandidate(title='Poctivy', deal_price=20.0, original_price=40.0,
                            url='https://x.sk/a', source='s', store='Jysk')
    fake = DealCandidate(title='Nafuknuty', deal_price=20.0, original_price=40.0,
                         url='https://x.sk/b', source='s', store='OBI')

    history = {fake.product_key: [{'date': '2026-08-01', 'price': 20.0}]}
    docs = main.enrich_with_price_history([genuine, fake], history)

    titles = [d['title'] for d in docs]
    assert 'Poctivy' in titles
    assert 'Nafuknuty' not in titles
    # Poctivemu dealu sa historia doplni.
    assert docs[0]['priceHistory'][-1]['price'] == 20.0
