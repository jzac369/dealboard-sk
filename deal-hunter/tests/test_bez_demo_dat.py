"""Ukážkové (demo) dealy z prototypu sa nesmú vrátiť do stránky.

Raz sa stalo, že funkcia v index.html zapísala vymyslené dealy so stavom
"approved" do ostrej databázy a návštevníci ich videli ako skutočné.
"""
from pathlib import Path

KOREN = Path(__file__).resolve().parents[2]
ZAKAZANE = ["DEMO_DEALS", "insertDemoIfEmpty", "demoInserted", "Demo režim", "Ukážkové dáta"]


def test_index_nema_demo_data():
    html = (KOREN / "index.html").read_text(encoding="utf-8")
    najdene = [z for z in ZAKAZANE if z in html]
    assert not najdene, f"V index.html sa vrátili demo dáta: {najdene}"


def test_klient_nezapisuje_dealy_cez_seed():
    html = (KOREN / "index.html").read_text(encoding="utf-8")
    # Jediné povolené miesto zápisu dealu z prehliadača je formulár "Pridať deal".
    assert html.count('addDoc(collection(db, "deals"),') == 1


def test_pravidla_vyzaduju_autora_aj_od_admina():
    pravidla = (KOREN / "firestore.rules").read_text(encoding="utf-8")
    zaciatok = pravidla.index("match /deals/{dealId}")
    blok = pravidla[zaciatok: zaciatok + 1500]
    import re
    assert not re.search(r"allow create: if isAdmin\(\);", blok)
