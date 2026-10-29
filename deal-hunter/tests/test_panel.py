"""Panel servera: overenie nastavení pred zápisom do databázy."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "panel"))

import panel  # noqa: E402


def test_prepusti_len_platne_hodnoty():
    ok, chyby = panel.over_nastavenia({
        "maxNaBeh": "3", "trhTolerancia": 0.02, "trhMinObchodov": 4, "trhKontrola": True,
        "vylucenaSlova": "vzorka, tester ,", "zdroje": ["feeds", "neexistuje"], "nieco": 5,
    })
    assert not chyby
    assert ok["maxNaBeh"] == 3 and isinstance(ok["maxNaBeh"], int)
    assert ok["trhTolerancia"] == 0.02
    assert ok["trhMinObchodov"] == 4
    assert ok["trhKontrola"] is True
    assert ok["vylucenaSlova"] == ["vzorka", "tester"]
    assert ok["zdroje"] == ["feeds"]
    assert "nieco" not in ok


def test_odmietne_mimo_rozsahu_a_prazdne_zdroje():
    _ok, chyby = panel.over_nastavenia({"maxNaBeh": 500, "zdroje": ["neexistuje"], "minZlava": "abc"})
    assert len(chyby) == 3


def test_pin_bez_suboru_neprejde(tmp_path, monkeypatch):
    monkeypatch.setattr(panel, "PIN_SUBOR", tmp_path / "nie.json")
    assert panel.over_pin("1234") is False
