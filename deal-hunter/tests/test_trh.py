"""Trhová kontrola: párovanie produktov s porovnávačom a rozhodnutie o najnižšej cene."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import trh  # noqa: E402

PM = "https://www.pricemania.sk/x/"


def _index(*slugy):
    # Doplníme veľa výplňových produktov, aby bežné slová neboli "vzácne".
    vypln = [f"{PM}znacka{i}-voda-olej-parfumovana-ml-tb-e/" for i in range(400)]
    return trh.Index([(u, trh.tokeny(u.rstrip("/").rsplit("/", 1)[-1]))
                      for u in [PM + s + "/" for s in slugy] + vypln])


def test_tokeny_jednotky_a_modely():
    assert trh.tokeny("Walmark Omega 3 180 tvrdých kapsúl") == ["walmark", "omega", "3", "180", "tvrdych", "tbl"]
    assert trh.tokeny("walmark-omega-3-180tbl") == ["walmark", "omega", "3", "180", "tbl"]
    # Krátka predpona patrí k modelu: S25 a A25 sú rôzne telefóny.
    assert "s25" in trh.tokeny("Samsung Galaxy S25") and "a25" in trh.tokeny("Samsung Galaxy A25")
    assert trh.tokeny("De'Longhi") == ["delonghi"]


def test_parovanie_spravny_produkt():
    idx = _index("walmark-omega-3-rybi-olej-forte-180tbl", "walmark-omega-3-rybi-olej-forte-60tbl")
    url, _ = idx.najdi("Walmark Omega 3 rybí olej FORTE 180 tvrdých kapsúl")
    assert url.endswith("forte-180tbl/")


def test_parovanie_odmietne_iny_model_a_iny_produkt():
    idx = _index("samsung-galaxy-a25-256gb", "xiaomi-redmi-buds-essential", "dino-kocky",
                 "lattafa-maahir-parfumovana-voda-100ml")
    assert idx.najdi("Samsung Galaxy S25 256GB") is None          # iný model
    assert idx.najdi("Xiaomi Redmi Buds 8 Lite") is None          # chýba číslo modelu
    assert idx.najdi("Dino DOPRAVA 6 Drevené kocky") is None       # všeobecný produkt bez '6'
    assert idx.najdi("Lattafa Yara 100 ml parfumovaná voda") is None  # iná vôňa


def test_posudenie_ceny():
    trh_data = {"najnizsia": 10.0, "najvyssia": 15.0, "obchodov": 5}
    assert trh.posud(9.5, trh_data)[0]
    assert trh.posud(10.05, trh_data)[0]           # do 1 % nad najnižšou
    assert not trh.posud(10.5, trh_data)[0]        # inde lacnejšie
    assert not trh.posud(5.0, {"najnizsia": 10.0, "najvyssia": 10.0, "obchodov": 1})[0]  # nedá sa porovnať
