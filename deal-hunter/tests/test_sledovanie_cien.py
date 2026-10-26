"""Sledovanie cien: čo sa kontroluje a kedy je zmena ceny hodná upozornenia."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sledovanie_cien as sc  # noqa: E402


class _Doc:
    def __init__(self, data):
        self._d = data

    def to_dict(self):
        return self._d


def test_zmena_ceny():
    assert sc.posudit_zmenu(100, 110) == "vyssia"
    assert sc.posudit_zmenu(100, 104) is None      # pod prahom
    assert sc.posudit_zmenu(100, 90) == "nizsia"
    assert sc.posudit_zmenu(0, 50) is None          # bez ceny v deale nehodnotíme
    assert sc.posudit_zmenu(50, 0) is None


def test_vyber_preskakuje_expirovane_letenky_a_blokovane_obchody():
    docs = [
        _Doc({"url": "https://a.sk/1", "title": "ok"}),
        _Doc({"url": "https://a.sk/2", "expired": True}),
        _Doc({"url": "https://allegro.sk/x"}),
        _Doc({"url": "https://www.ryanair.com/y", "category": "Cestovanie"}),
        _Doc({"url": "https://b.sk/3", "category": "Cestovanie"}),
        _Doc({"title": "bez adresy"}),
    ]
    vybrane = sc.vyber_na_kontrolu(docs)
    assert [u for _d, u in vybrane] == ["https://a.sk/1"]


def test_vyber_najstarsia_kontrola_prva_a_limit():
    docs = [
        _Doc({"url": "https://a.sk/nova", "cenaKontrola": "2026-10-25"}),
        _Doc({"url": "https://a.sk/nikdy"}),
        _Doc({"url": "https://a.sk/stara", "cenaKontrola": "2026-10-01"}),
    ]
    vybrane = sc.vyber_na_kontrolu(docs, limit=2)
    # Nikdy nekontrolovaný (prázdny reťazec) je prvý, potom najstarší dátum.
    assert [u for _d, u in vybrane] == ["https://a.sk/nikdy", "https://a.sk/stara"]


def test_porovnatelnost_ceny():
    ok = {"title": "Vitamín C", "dealPrice": 10.0}
    assert sc.je_porovnatelna(ok, 11.0)
    assert not sc.je_porovnatelna(ok, 25.0)                       # iný variant
    assert not sc.je_porovnatelna(ok, 3.0)
    assert not sc.je_porovnatelna({"title": "TV s kódom ABC10", "dealPrice": 400.0}, 600.0)
    assert not sc.je_porovnatelna({"title": "x", "dealPrice": 0}, 5.0)
