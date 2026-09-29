"""
Zdieľanie schválených dealov na facebookovú stránku.

ČO TO STOJÍ
Nič. Graph API je na publikovanie na vlastnú stránku zadarmo a bez
limitu, ktorý by sme pri troch-piatich príspevkoch denne dosiahli.
Potrebná je len aplikácia na developers.facebook.com a prístupový
token stránky - to je jednorazové nastavenie, nie poplatok.

ČO SA POSIELA
Odkaz na vlastnú stránku dealu (/deal/...), nie rovno do e-shopu.
Dôvody sú dva: Facebook z nej vytiahne fotku a titulok cez Open Graph
značky, a návštevník sa dostane k nám, nie priamo preč.

K odkazu pridávame UTM značky, takže v admine vidno, koľko ľudí prišlo
z Facebooku a koľko z nich kliklo ďalej.

PREČO SA NEPOSIELA HNEĎ
Stránku dealu generuje GitHub Actions a chvíľu trvá, kým ju GitHub
Pages naozaj vydá. Keby sme Facebooku poslali odkaz skôr, stiahol by si
404 a to si zapamätá - náhľad by potom zostal prázdny aj po oprave.
Preto sa pred odoslaním overí, že adresa odpovedá 200; ak nie, deal
počká na ďalší beh.

Nastavenie (GitHub secrets):
  FB_PAGE_ID      číselné ID facebookovej stránky
  FB_PAGE_TOKEN   dlhodobý prístupový token tej stránky

Bez nich skript nič neurobí a skončí v poriadku.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import requests
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

import config
import firestore_client

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("facebook")

STRANKA = os.environ.get("FB_PAGE_ID", "").strip()
TOKEN = os.environ.get("FB_PAGE_TOKEN", "").strip()
API = "https://graph.facebook.com/v21.0"

SITE = "https://henkukaj.sk"

# Koľko dealov najviac za jeden beh. Vysypať naraz desať príspevkov je
# najrýchlejšia cesta k tomu, aby ľudia stránku prestali sledovať.
MAX_ZA_BEH = int(os.environ.get("FB_MAX_PER_RUN", 2))

# Staršie dealy nezdieľame vôbec. Pri prvom zapnutí je na stránke
# päťdesiat schválených dealov bez značky o zdieľaní; bez tohto
# obmedzenia by sa postupne vysypali všetky, vrátane tých spred
# mesiaca. Zdieľame len to, čo je naozaj nové.
MAX_VEK_DNI = int(os.environ.get("FB_MAX_AGE_DAYS", 3))

ZNACKY = "utm_source=facebook&utm_medium=social&utm_campaign=auto"


def _slug(text: str) -> str:
    """
    Rovnaký tvar adresy, aký vyrába generate_deal_pages.py.

    Musí to byť znak po znaku to isté. Keby sa líšili čo i len v
    orezaní, odkaz by viedol na neexistujúcu stránku, kontrola nižšie
    by ju nenašla a deal by sa nezdieľal nikdy - ticho, bez chyby.
    """
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:60].strip("-") or "deal"


def adresa_dealu(deal_id: str, titul: str) -> str:
    return f"{SITE}/deal/{_slug(titul)}-{deal_id}/"


def _je_dostupna(url: str) -> bool:
    try:
        r = requests.head(url, timeout=20, allow_redirects=True)
        return r.status_code == 200
    except Exception as e:
        logger.warning("Stránku %s sa nepodarilo overiť: %s", url, e)
        return False


def sprava(d: dict) -> str:
    cena = d.get("dealPrice")
    povodna = d.get("originalPrice")
    zlava = d.get("discountPercent") or 0

    riadky = [d.get("title", "").strip()]
    if cena:
        c = f"{float(cena):.2f}".replace(".", ",")
        if povodna and zlava:
            p = f"{float(povodna):.2f}".replace(".", ",")
            riadky.append(f"Teraz {c} € namiesto {p} € (−{zlava} %)")
        else:
            riadky.append(f"Cena {c} €")
    if d.get("store"):
        riadky.append(f"Predajca: {d['store']}")
    riadky.append("")
    riadky.append("Viac na HenKukaj.sk")
    return "\n".join(r for r in riadky if r is not None)


def posli(db) -> int:
    if not (STRANKA and TOKEN):
        logger.info("FB_PAGE_ID alebo FB_PAGE_TOKEN nie sú nastavené — nezdieľam nič.")
        return 0

    try:
        dokumenty = list(
            db.collection(config.DEALS_COLLECTION)
            .where(filter=FieldFilter("status", "==", "approved"))
            .stream()
        )
    except Exception as e:
        logger.error("Dealy sa nepodarilo načítať: %s", e)
        return 0

    # Len tie, ktoré sme ešte nezdieľali, neuplynula im platnosť a nie sú
    # staré. Vek počítame z času pridania.
    hranica = datetime.now(timezone.utc) - timedelta(days=MAX_VEK_DNI)
    cakajuce = []
    for doc in dokumenty:
        d = doc.to_dict() or {}
        if d.get("fbPosted") or d.get("expired"):
            continue
        t = d.get("timestamp")
        try:
            if not t or t.replace(tzinfo=timezone.utc) < hranica:
                continue
        except Exception:
            continue
        cakajuce.append((doc.id, d))
    # Od najnovších - staršie dealy už nikoho neprekvapia.
    cakajuce.sort(key=lambda t: str(t[1].get("timestamp")), reverse=True)

    if not cakajuce:
        logger.info("Nič nové na zdieľanie.")
        return 0

    logger.info("Nezdieľaných dealov: %d, poslať môžem najviac %d",
                len(cakajuce), MAX_ZA_BEH)

    poslane = 0
    for deal_id, d in cakajuce:
        if poslane >= MAX_ZA_BEH:
            break

        url = adresa_dealu(deal_id, d.get("title", ""))
        if not _je_dostupna(url):
            logger.info("Stránka %s ešte nie je vydaná — deal počká na ďalší beh.", url)
            continue

        odkaz = f"{url}?{ZNACKY}"
        try:
            r = requests.post(
                f"{API}/{STRANKA}/feed",
                data={"message": sprava(d), "link": odkaz, "access_token": TOKEN},
                timeout=40,
            )
        except Exception as e:
            logger.error("Odoslanie zlyhalo: %s", e)
            continue

        if r.status_code != 200:
            # Chybu vypisujeme celú okrem tokenu - bez nej sa nedá zistiť,
            # či ide o vypršaný token alebo o chýbajúce oprávnenie.
            text = r.text.replace(TOKEN, "***") if TOKEN else r.text
            logger.error("Facebook odmietol príspevok (HTTP %s): %s",
                         r.status_code, text[:300])
            continue

        prispevok = (r.json() or {}).get("id", "")
        logger.info("Zdieľané: %s", d.get("title", "")[:60])

        try:
            db.collection(config.DEALS_COLLECTION).document(deal_id).update({
                "fbPosted": True,
                "fbPostId": prispevok,
                "fbPostedAt": firestore.SERVER_TIMESTAMP,
            })
        except Exception as e:
            # Príspevok už na Facebooku je. Keď sa značka nezapíše,
            # zdieľal by sa druhýkrát - preto je to chyba, nie varovanie.
            logger.error("Deal %s sa nepodarilo označiť ako zdieľaný: %s", deal_id, e)

        poslane += 1

    logger.info("Zdieľaných príspevkov: %d", poslane)
    return poslane


def main() -> int:
    logger.info("=== Zdieľanie na Facebook ===")
    db = firestore_client.get_client()
    posli(db)
    logger.info("=== Koniec ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
