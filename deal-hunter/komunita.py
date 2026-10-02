"""
Komunita: body, odznaky, rebríček a dôveryhodní prispievatelia.

PREČO TO POČÍTA PLÁNOVAČ A NIE STRÁNKA
Body by si inak vedel ktokoľvek dopísať sám - stačilo by otvoriť konzolu
prehliadača. Preto ich počíta tento skript cez service account a zapisuje
do kolekcií, do ktorých stránka smie len čítať (prispievatelia, verejne,
duveryhodni).

ČO SA POČÍTA
  10 bodov za zverejnený deal, 1 bod za každý hlas, 1 bod za 5 preklikov.
  Zamietnutý deal -5 bodov, aby sa neoplatilo posielať čokoľvek.
Odznak je len prah v bodoch (Nováčik → Legenda).

DÔVERYHODNÝ PRISPIEVATEĽ
Kto má aspoň N zverejnených dealov a dosť vysokú úspešnosť, zapíše sa do
duveryhodni/{uid} a jeho ďalšie dealy idú na stránku rovno. Podmienky
nastavuje admin (nastavenia_admin/komunita). Rovnakú podmienku vymáhajú
aj pravidlá databázy, takže sa to nedá obísť formulárom.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("komunita")

ODZNAKY = [
    (0, "🌱", "Nováčik"), (50, "🔎", "Lovec zliav"), (200, "⭐", "Skúsený lovec"),
    (500, "🏅", "Majster zliav"), (1500, "👑", "Legenda"),
]

PREDVOLENE = {
    "zapnute": True,
    "bodyZaDeal": 10,
    "bodyZaHlas": 1,
    "bodyZa5Preklikov": 1,
    "bodyZaZamietnuty": -5,
    "doveraZapnuta": False,
    "doveraMinDealov": 5,
    "doveraMinUspesnost": 80,
    "doveraMinBodov": 50,
}


def odznak(body: int) -> tuple[str, str]:
    ikona, nazov = ODZNAKY[0][1], ODZNAKY[0][2]
    for prah, i, n in ODZNAKY:
        if body >= prah:
            ikona, nazov = i, n
    return ikona, nazov


def nastavenia(db) -> dict:
    try:
        d = db.document("nastavenia_admin/komunita").get().to_dict() or {}
    except Exception as e:
        logger.warning("Nastavenia komunity sa nepodarilo načítať: %s", e)
        d = {}
    return {**PREDVOLENE, **{k: v for k, v in d.items() if v is not None}}


def _kliky(db) -> dict:
    try:
        return {d.id: (d.to_dict() or {}).get("count", 0) for d in db.collection("deal_clicks").stream()}
    except Exception:
        return {}


def prepocitaj(db) -> int:
    """Prepočíta body všetkých prispievateľov. Vráti ich počet."""
    n = nastavenia(db)
    if not n["zapnute"]:
        return 0
    try:
        dealy = list(db.collection("deals").stream())
        pouzivatelia = {d.id: (d.to_dict() or {}) for d in db.collection("users").stream()}
    except Exception as e:
        logger.warning("Dealy alebo používateľov sa nepodarilo načítať: %s", e)
        return 0
    kliky = _kliky(db)

    ludia: dict[str, dict] = {}
    for doc in dealy:
        d = doc.to_dict() or {}
        uid = d.get("authorUid")
        # Deal od agenta ani od admina do rebríčka nepatrí - je to rebríček ľudí.
        if not uid or uid not in pouzivatelia:
            continue
        o = ludia.setdefault(uid, {"dealy": 0, "hlasy": 0, "kliky": 0, "zamietnute": 0, "posledny": None})
        if d.get("status") in ("approved", "archived"):
            o["dealy"] += 1
            o["hlasy"] += max(0, int(d.get("votes") or 0))
            o["kliky"] += int(kliky.get(doc.id, 0))
            t = d.get("timestamp")
            if t and (o["posledny"] is None or t > o["posledny"]):
                o["posledny"] = t
        elif d.get("status") == "rejected":
            o["zamietnute"] += 1

    zapisane = []
    batch = db.batch()
    for uid, o in ludia.items():
        p = pouzivatelia.get(uid) or {}
        body = (o["dealy"] * n["bodyZaDeal"] + o["hlasy"] * n["bodyZaHlas"]
                + (o["kliky"] // 5) * n["bodyZa5Preklikov"] + o["zamietnute"] * n["bodyZaZamietnuty"])
        body = max(0, int(body))
        ikona, nazov = odznak(body)
        meno = (p.get("meno") or (p.get("email") or "").split("@")[0] or "Anonym").strip()[:40]
        rozhodnute = o["dealy"] + o["zamietnute"]
        zapisane.append({
            "uid": uid, "meno": meno, "body": body, "dealy": o["dealy"], "hlasy": o["hlasy"],
            "kliky": o["kliky"], "zamietnute": o["zamietnute"], "odznak": ikona, "odznakNazov": nazov,
            "uspesnost": round(o["dealy"] / rozhodnute * 100) if rozhodnute else 0,
            "posledny": o["posledny"],
        })

    zapisane.sort(key=lambda x: (-x["body"], -x["dealy"], x["meno"]))
    from google.cloud import firestore
    for poradie, x in enumerate(zapisane, 1):
        x["poradie"] = poradie
        batch.set(db.collection("prispevatelia").document(x["uid"]), {
            **{k: v for k, v in x.items() if k != "uid"},
            "aktualizovane": firestore.SERVER_TIMESTAMP,
        })
    # Rebríček a odznaky autorov pre stránku - jeden dokument, jedno čítanie.
    batch.set(db.document("verejne/rebricek"), {
        "top": [{"meno": x["meno"], "body": x["body"], "dealy": x["dealy"], "hlasy": x["hlasy"], "odznak": x["odznak"]}
                for x in zapisane[:20]],
        "odznaky": {x["meno"].lower(): {"ikona": x["odznak"], "nazov": x["odznakNazov"], "body": x["body"]}
                    for x in zapisane[:100] if x["body"] >= 50},
        "spolu": len(zapisane),
        "aktualizovane": firestore.SERVER_TIMESTAMP,
    })
    batch.commit()

    if n["doveraZapnuta"]:
        _dovera(db, n, zapisane)
    logger.info("Komunita: prepočítaných %d prispievateľov", len(zapisane))
    return len(zapisane)


def _dovera(db, n: dict, ludia: list[dict]) -> None:
    """Udelí a odoberie dôveru podľa pravidiel z adminu."""
    from google.cloud import firestore

    try:
        teraz = {d.id for d in db.collection("duveryhodni").stream()}
    except Exception as e:
        logger.warning("Dôveryhodných sa nepodarilo načítať: %s", e)
        return
    maju = set()
    batch = db.batch()
    zmeny = 0
    for x in ludia:
        ok = (x["dealy"] >= n["doveraMinDealov"] and x["uspesnost"] >= n["doveraMinUspesnost"]
              and x["body"] >= n["doveraMinBodov"])
        if ok:
            maju.add(x["uid"])
            if x["uid"] not in teraz:
                batch.set(db.collection("duveryhodni").document(x["uid"]), {
                    "meno": x["meno"], "dealy": x["dealy"], "uspesnost": x["uspesnost"], "body": x["body"],
                    "od": firestore.SERVER_TIMESTAMP, "dovod": "automaticky podľa pravidiel",
                })
                zmeny += 1
                logger.info("Dôvera udelená: %s (%d dealov, %d %%)", x["meno"], x["dealy"], x["uspesnost"])
    # Komu podmienky prestali vychádzať (napr. pribudli zamietnutia),
    # dôveru odoberieme - ale len tomu, koho sme ju udelili sami.
    for uid in teraz - maju:
        d = db.collection("duveryhodni").document(uid).get().to_dict() or {}
        if d.get("dovod", "").startswith("automaticky"):
            batch.delete(db.collection("duveryhodni").document(uid))
            zmeny += 1
    if zmeny:
        batch.commit()


def nove_dealy_pre_strazcov(db, od: datetime) -> list[dict]:
    """Dealy zverejnené po čase `od` - podklad pre strážcov a letenky."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    try:
        docs = list(db.collection("deals").where(filter=FieldFilter("status", "==", "approved")).stream())
    except Exception as e:
        logger.warning("Dealy pre strážcov sa nepodarilo načítať: %s", e)
        return []
    nove = []
    for doc in docs:
        d = doc.to_dict() or {}
        t = d.get("timestamp")
        if not t or d.get("expired"):
            continue
        try:
            if t < od:
                continue
        except TypeError:
            continue
        nove.append({**d, "id": doc.id})
    nove.sort(key=lambda d: d.get("timestamp") or datetime.now(timezone.utc), reverse=True)
    return nove
