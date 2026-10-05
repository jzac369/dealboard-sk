"""
Zaraďovanie do kategórií - najmä čo NIE je elektronika.

Agent 5. 10. 2026 navrhol ako "Elektronika" zinok na cmúľanie, prací gél
aj dámske nohavice. Všetky tri majú v názve slovo, ktoré sa dovtedy
bralo ako elektronika ("tablet", "mobil"), a skutočná elektronika sa
v tom šume stratila.
"""
import pytest

from models import guess_category


@pytest.mark.parametrize("nazov", [
    "GymBeam Zinok, tablety na cmúľanie malina",
    "Ariel gélové tablety 2 druhy 10-12 ks",
    "CRIVIT Dámske funkčné capri nohavice, vysoký pás, s vrecko na mobil",
    "Pracie tablety Persil 40 ks",
])
def test_nie_je_elektronika(nazov):
    assert guess_category(nazov) != "Elektronika"


@pytest.mark.parametrize("nazov", [
    "Apple iPhone 15 128GB čierny",
    "Samsung televízor 55\" QLED",
    "Lenovo notebook IdeaPad 5",
    "Xiaomi tablet Redmi Pad SE",
    "Bezdrôtové slúchadlá JBL Tune",
    "Powerbank Anker 20000 mAh",
])
def test_je_elektronika(nazov):
    assert guess_category(nazov) == "Elektronika"


def test_nohavice_su_moda():
    assert guess_category("CRIVIT Dámske capri nohavice s vreckom na mobil") == "Móda"


def test_pokyn_z_feedu_ma_prednost():
    # Keď zdroj kategóriu uvedie, hádať ju nemusíme.
    assert guess_category("Čokoľvek", hint="Elektronika") == "Elektronika"
