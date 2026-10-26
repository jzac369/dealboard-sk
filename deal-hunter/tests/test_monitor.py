"""Kontrola webu: kedy sa oznamuje výpadok a kedy obnovenie."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import monitor  # noqa: E402


def _priprav(monkeypatch, tmp_path, odpovede):
    """odpovede = zoznam, z ktorého sa berie výsledok jednej kontroly (ok, dovod)."""
    monkeypatch.setattr(monitor, "STAV_SUBOR", tmp_path / "stav.json")
    monkeypatch.setattr(monitor, "SKUSKA", False)
    monkeypatch.setattr(monitor, "KONTROLY", [("web", "https://x.test/", None)])
    sprav = []
    monkeypatch.setattr(monitor, "posli", lambda t: sprav.append(t))
    it = iter(odpovede)
    monkeypatch.setattr(monitor, "skontroluj", lambda *a: next(it))
    return sprav


def test_jedno_zlyhanie_nic_neoznamuje(monkeypatch, tmp_path):
    sprav = _priprav(monkeypatch, tmp_path, [(False, "HTTP 500"), (True, "ok")])
    monitor.kontrola_webu()
    monitor.kontrola_webu()
    assert sprav == []


def test_dve_zlyhania_oznamia_raz_a_potom_obnovenie(monkeypatch, tmp_path):
    sprav = _priprav(monkeypatch, tmp_path,
                     [(False, "HTTP 500"), (False, "HTTP 500"), (False, "HTTP 500"), (True, "ok")])
    for _ in range(4):
        monitor.kontrola_webu()
    # Výpadok sa oznámi práve raz (nie pri treťom zlyhaní znova) + obnovenie.
    assert len(sprav) == 2
    assert sprav[0].startswith("Výpadok: web")
    assert sprav[1].startswith("Obnovené: web")


def test_skuska_nic_neposiela_ani_nezapisuje(monkeypatch, tmp_path):
    _priprav(monkeypatch, tmp_path, [(False, "HTTP 500"), (False, "HTTP 500")])
    monkeypatch.setattr(monitor, "SKUSKA", True)
    monitor.kontrola_webu()
    monitor.kontrola_webu()
    assert not (tmp_path / "stav.json").exists()
