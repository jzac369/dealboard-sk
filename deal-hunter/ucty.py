"""
E-maily o účte (overenie adresy) v našom vzhľade.

PREČO TO NEROBÍ FIREBASE
Firebase vie taký e-mail poslať sám, ale jeho text sa upraviť nedá -
telo šablóny "Email address verification" je v konzole zamknuté, aby sa
služba nedala zneužiť na rozosielanie. Zostal by teda anglický text
s odkazom na dealboard-e60bf.firebaseapp.com.

Preto si odkaz vypýtame cez Identity Toolkit (returnOobLink), prepíšeme
ho na našu stránku a e-mail pošleme vlastnou schránkou v rovnakom
vzhľade ako ostatné naše e-maily.

AKO SA SEM ÚLOHA DOSTANE
Stránka po registrácii (alebo po kliknutí na "Poslať znova") zapíše
dokument do kolekcie ucty_akcie. Plánovač ju sleduje živým odberom, takže
e-mail odíde do pár sekúnd. Zapísať ju smie len prihlásený človek a len
pre svoju vlastnú adresu - inak by sa dala zneužiť na posielanie pošty
na cudzie adresy.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlencode, urlparse

import google.auth.transport.requests
import requests
from google.oauth2 import service_account

import config
import emaily

logger = logging.getLogger("ucty")

NASA_AKCIA = "https://henkukaj.sk/ucet-akcia.html"
API = "https://identitytoolkit.googleapis.com/v1"

PREDMETY = {
    "overenie": "Potvrď svoj e-mail na HenKukaj.sk",
}


def _session():
    cred = service_account.Credentials.from_service_account_file(
        config.FIREBASE_CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/cloud-platform",
                "https://www.googleapis.com/auth/firebase"],
    )
    return google.auth.transport.requests.AuthorizedSession(cred)


def odkaz(typ: str, email: str) -> str:
    """
    Vypýta si jednorazový odkaz od Firebase a prepíše ho na našu stránku.

    Vraciame vlastnú adresu bez ohľadu na nastavenie v konzole - takto
    e-mail odkazuje na henkukaj.sk aj keď v konzole nikto nič nemenil.
    """
    druh = {"overenie": "VERIFY_EMAIL", "heslo": "PASSWORD_RESET"}[typ]
    r = _session().post(
        f"{API}/projects/{config.FIRESTORE_PROJECT_ID}/accounts:sendOobCode",
        json={"requestType": druh, "email": email, "returnOobLink": True},
        timeout=30,
    )
    if r.status_code != 200:
        chyba = (r.json().get("error") or {}).get("message", r.text[:200])
        raise ValueError(f"Firebase odkaz nevydal: {chyba}")
    povodny = (r.json() or {}).get("oobLink") or ""
    p = parse_qs(urlparse(povodny).query)
    kod = (p.get("oobCode") or [""])[0]
    mod = (p.get("mode") or [""])[0]
    if not kod:
        raise ValueError("Firebase nevrátil kód odkazu.")
    return NASA_AKCIA + "?" + urlencode({
        "mode": mod or ("verifyEmail" if typ == "overenie" else "resetPassword"),
        "oobCode": kod,
        "continueUrl": "https://henkukaj.sk/?ucet=overeny",
    })


TEXT_OVERENIE = (
    "Ahoj{meno},\n\nvitaj na HenKukaj.sk! Ešte jeden klik a máš hotovo – potvrď, že tento e-mail patrí tebe.\n\n"
    "Potom si môžeš ukladať dealy, nastaviť si strážcu zliav a dostávať len to, čo ťa naozaj zaujíma.\n\n"
    "Ak si sa neregistroval ty, tento e-mail pokojne zahoď. Bez potvrdenia sa nič nestane.\n\n"
    "Tím HenKukaj.sk"
)


def posli_overenie(db, email: str, meno: str = "") -> None:
    n = emaily.nastavenia(db)
    text = TEXT_OVERENIE.format(meno=f" {meno}" if meno else "")
    emaily.posli(n, email, PREDMETY["overenie"], text,
                 tlacidlo=("Potvrdiť e-mail", odkaz("overenie", email)))


def spracuj(db, ref) -> None:
    """Vykoná jednu žiadosť z kolekcie ucty_akcie."""
    from google.cloud import firestore

    @firestore.transactional
    def prevezmi(tx):
        snap = ref.get(transaction=tx)
        d = snap.to_dict() or {}
        if not snap.exists or d.get("stav") != "caka":
            return None
        tx.update(ref, {"stav": "bezi"})
        return d

    data = prevezmi(db.transaction())
    if not data:
        return
    email = str(data.get("email") or "").strip()
    typ = data.get("typ")
    try:
        if typ != "overenie" or "@" not in email:
            raise ValueError(f"Neznáma žiadosť: {typ}")
        if not os.environ.get("SMTP_PASSWORD"):
            raise ValueError("Chýba heslo k schránke (SMTP_PASSWORD).")
        # Aby sa tlačidlom "Poslať znova" nedalo niekoho zasypať poštou.
        nedavno = datetime.now(timezone.utc) - timedelta(minutes=10)
        poslane = [d for d in db.collection("email_log")
                   .where("typ", "==", "overenie").where("komu", "==", email).stream()
                   if (d.to_dict() or {}).get("kedy") and d.to_dict()["kedy"] > nedavno]
        if len(poslane) >= 3:
            raise ValueError("Priveľa pokusov za sebou, skús o pár minút.")
        posli_overenie(db, email, str(data.get("meno") or ""))
        emaily.zapis(db, None, {"typ": "overenie", "komu": email, "ok": True})
        ref.update({"stav": "hotovo", "koniec": firestore.SERVER_TIMESTAMP})
        logger.info("Overovací e-mail odoslaný: %s", email)
    except Exception as e:
        logger.warning("Overovací e-mail pre %s zlyhal: %s", email, e)
        emaily.zapis(db, None, {"typ": "overenie", "komu": email, "ok": False, "chyba": str(e)[:300]})
        ref.update({"stav": "chyba", "chyba": str(e)[:300], "koniec": firestore.SERVER_TIMESTAMP})


def sleduj(db, fronta) -> object | None:
    """Živý odber čakajúcich žiadostí - ID dokumentov dáva do fronty."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    def zmena(_snimky, zmeny, _cas):
        for z in zmeny:
            if z.type.name in ("ADDED", "MODIFIED"):
                fronta.put(z.document.reference)

    try:
        return (db.collection("ucty_akcie")
                .where(filter=FieldFilter("stav", "==", "caka"))
                .on_snapshot(zmena))
    except Exception as e:
        logger.warning("Odber žiadostí o e-mail sa nepodarilo spustiť: %s", e)
        return None


def dobehni(db) -> int:
    """Žiadosti, ktoré ostali čakať (napr. keď plánovač práve nebežal)."""
    from google.cloud.firestore_v1.base_query import FieldFilter

    try:
        docs = list(db.collection("ucty_akcie").where(filter=FieldFilter("stav", "==", "caka")).stream())
    except Exception as e:
        logger.warning("Čakajúce žiadosti sa nepodarilo načítať: %s", e)
        return 0
    for d in docs:
        spracuj(db, d.reference)
    return len(docs)
