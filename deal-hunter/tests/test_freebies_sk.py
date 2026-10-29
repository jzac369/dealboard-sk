"""Slovenské freebies: darčeky k nákupu zo stránky a položky za 0 € z feedov."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import DealCandidate  # noqa: E402
from scrapers.feeds import FeedsScraper  # noqa: E402
from scrapers.freebies_sk import darcek_zo_stranky  # noqa: E402


def test_darcek_k_nakupu_zo_stranky():
    html = ('<html><head><meta property="og:image" content="https://x/i.jpg"></head><body>'
            '<div>DARČEK ZADARMO V HODNOTE 10 € A VIAC K NÁKUPU NAD 50 €</div><p>Proteíny</p></body></html>')
    c = darcek_zo_stranky("https://gymbeam.sk/", html)
    assert c is not None and c.zadarmo
    assert "k nákupu nad 50 €" in c.title.lower()
    assert "nejde o produkt úplne zadarmo" in c.description.lower()


def test_bez_vety_o_darceku_nic():
    assert darcek_zo_stranky("https://x.sk/", "<p>Akcia -20 % na všetko</p>") is None


def _c(nazov, cena, popis=""):
    return DealCandidate(title=nazov, deal_price=cena, url=f"https://obchod.sk/{nazov}", source="feeds",
                         direct_url=True, store="Obchod.sk", description=popis)


def test_feed_vzorka_za_0_je_freebie_a_nula_bez_slova_nie():
    vyber = FeedsScraper._vyber([
        _c("Vzorka Whey 30g", 0.0), _c("Šejker", 0.0, "Darček zadarmo k objednávke"),
        _c("Notebook", 0.0), _c("Proteín 1kg", 25.0),
    ], "https://feed.obchod.sk/x.xml")
    zadarmo = [c for c in vyber if c.zadarmo]
    assert sorted(c.title.split(" – ")[0] for c in zadarmo) == ["Vzorka Whey 30g", "Šejker"]
    assert all("zadarmo k objednávke" in c.title for c in zadarmo)
    assert not any(c.title == "Notebook" for c in vyber)      # 0 € bez slova = chýbajúca cena
