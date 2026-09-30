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


def token_stranky() -> str | None:
    """
    Vráti token, ktorým sa dá publikovať na stránku.

    PREČO TO NIE JE JEDNODUCHO FB_PAGE_TOKEN
    Vyžiadať v Graph API Explorerovi token stránky a ešte ho aj predĺžiť
    je prekvapivo ľahké pokaziť - Access Token Debugger predlžuje token,
    ktorý mu dáš, a keď mu dáš používateľský, dostaneš späť predĺžený
    používateľský. Tým sa na stránku publikovať nedá.

    Preto to neriešime návodom, ale kódom: keď je nastavený používateľský
    token, vypýtame si zoznam stránok, ktoré spravuje, a použijeme token
    tej našej. Token stránky odvodený z dlhodobého používateľského
    nevyprší.

    Odvodený token sa nikde nezapisuje ani nevypisuje - žije len v pamäti
    počas behu.
    """
    try:
        r = requests.get(f"{API}/me", params={"fields": "id", "access_token": TOKEN}, timeout=30)
        d = r.json()
    except Exception as e:
        logger.error("Nepodarilo sa overiť token: %s", e)
        return None

    if "error" in d:
        logger.error("Token neprešiel: %s", str(d["error"].get("message"))[:200])
        return None

    if str(d.get("id")) == STRANKA:
        logger.info("Nastavený token patrí priamo stránke.")
        return TOKEN

    logger.info("Nastavený token patrí používateľovi — odvodzujem z neho token stránky.")
    try:
        r2 = requests.get(f"{API}/me/accounts",
                          params={"fields": "id,access_token", "access_token": TOKEN}, timeout=30)
        d2 = r2.json()
    except Exception as e:
        logger.error("Zoznam stránok sa nepodarilo načítať: %s", e)
        return None

    if "error" in d2:
        logger.error("Zoznam stránok odmietnutý: %s", str(d2["error"].get("message"))[:200])
        return None

    for s in d2.get("data", []):
        if str(s.get("id")) == STRANKA and s.get("access_token"):
            logger.info("Token stránky odvodený.")
            return s["access_token"]

    logger.error("Medzi stránkami tohto účtu nie je žiadna s ID z FB_PAGE_ID.")
    return None


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
    elif zlava:
        riadky.append(f"Zľava {round(zlava)} %")
    if d.get("store"):
        riadky.append(f"Predajca: {d['store']}")
    riadky.append("")
    riadky.append("Viac na HenKukaj.sk")
    return "\n".join(r for r in riadky if r is not None)


def posli(db) -> int:
    if not (STRANKA and TOKEN):
        logger.info("FB_PAGE_ID alebo FB_PAGE_TOKEN nie sú nastavené — nezdieľam nič.")
        return 0

    token = token_stranky()
    if not token:
        logger.error("Bez tokenu stránky sa publikovať nedá — končím.")
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
                data={"message": sprava(d), "link": odkaz, "access_token": token},
                timeout=40,
            )
        except Exception as e:
            logger.error("Odoslanie zlyhalo: %s", e)
            continue

        if r.status_code != 200:
            # Chybu vypisujeme celú okrem tokenu - bez nej sa nedá zistiť,
            # či ide o vypršaný token alebo o chýbajúce oprávnenie.
            text = r.text
            for tajne in (TOKEN, token):
                if tajne:
                    text = text.replace(tajne, "***")
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


def diagnostika() -> int:
    """
    Zistí, prečo Facebook odmieta príspevky.

    Zámerne nevypisuje token ani ID - len to, čo z nich vyplýva. Chyba
    "Object with ID does not exist" má tri bežné príčiny a bez tohto sa
    nedá rozlíšiť ktorú:
      - FB_PAGE_ID je ID osobného profilu, nie stránky
      - token patrí používateľovi, nie stránke
      - token stránke patrí, ale chýba mu oprávnenie
    """
    if not (STRANKA and TOKEN):
        logger.error("FB_PAGE_ID alebo FB_PAGE_TOKEN nie sú nastavené.")
        return 1

    logger.info("Dĺžka tokenu: %d znakov, dĺžka ID: %d znakov (samé číslice: %s)",
                len(TOKEN), len(STRANKA), STRANKA.isdigit())

    # 1. Komu token patrí
    try:
        r = requests.get(f"{API}/me", params={"fields": "id,name", "access_token": TOKEN}, timeout=30)
        d = r.json()
    except Exception as e:
        logger.error("Volanie /me zlyhalo: %s", e)
        return 1

    if "error" in d:
        logger.error("Token neprešiel: %s", str(d["error"].get("message"))[:200])
        return 1

    logger.info("Token patrí objektu s názvom: %r", d.get("name"))
    logger.info("ID z tokenu sa rovná FB_PAGE_ID: %s", str(d.get("id")) == STRANKA)

    # 2. Je to token stránky? Stránka má pole 'category', profil nie.
    r2 = requests.get(f"{API}/me", params={"fields": "category,fan_count", "access_token": TOKEN}, timeout=30)
    d2 = r2.json()
    if "error" in d2:
        logger.warning("Token nevie prečítať údaje stránky → vyzerá to na POUŽÍVATEĽSKÝ token, nie token stránky.")
    else:
        logger.info("Token vie čítať údaje stránky (kategória %r) → je to token stránky.",
                    d2.get("category"))

    # 3. Dá sa cez tento token načítať objekt, na ktorý publikujeme?
    r3 = requests.get(f"{API}/{STRANKA}", params={"fields": "name,category", "access_token": TOKEN}, timeout=30)
    d3 = r3.json()
    if "error" in d3:
        logger.error("FB_PAGE_ID sa cez tento token načítať nedá: %s",
                     str(d3["error"].get("message"))[:200])
    else:
        logger.info("FB_PAGE_ID ukazuje na %r (kategória %r)", d3.get("name"), d3.get("category"))

    # 4. Ktoré oprávnenia má účet aplikácii naozaj udelené. Odvodený
    # token stránky ich dedí z používateľského, takže keď tu niečo
    # chýba, publikovanie zlyhá bez ohľadu na to, čo je nastavené v
    # aplikácii - udelenie je vec toho prihlásenia, nie nastavenia.
    r5 = requests.get(f"{API}/me/permissions", params={"access_token": TOKEN}, timeout=30)
    d5 = r5.json()
    if "data" in d5:
        udelene = {p["permission"] for p in d5["data"] if p.get("status") == "granted"}
        logger.info("Udelené oprávnenia: %s", ", ".join(sorted(udelene)) or "žiadne")
        for treba in ("pages_manage_posts", "pages_read_engagement", "pages_show_list"):
            logger.info("   %-24s %s", treba, "OK" if treba in udelene else "CHÝBA")
    else:
        logger.warning("Zoznam oprávnení sa nepodarilo načítať.")

    # 5. Ak je to používateľský token, ukážeme, aké stránky spravuje.
    r4 = requests.get(f"{API}/me/accounts", params={"fields": "id,name", "access_token": TOKEN}, timeout=30)
    d4 = r4.json()
    if "data" in d4:
        logger.info("Stránky dostupné cez tento token: %d", len(d4["data"]))
        for s in d4["data"][:5]:
            zhoda = "  <-- toto ID máš v FB_PAGE_ID" if str(s.get("id")) == STRANKA else ""
            # ID stránky je verejný údaj (je v adrese stránky), takže ho
            # vypísať môžeme - a bez neho by sa chyba opravovala naslepo.
            logger.info("   %r  ID: %s%s", s.get("name"), s.get("id"), zhoda)
        if d4["data"] and not any(str(s.get("id")) == STRANKA for s in d4["data"]):
            logger.error("ŽIADNA z týchto stránok nemá ID, ktoré je vo FB_PAGE_ID.")
    return 0


def main() -> int:
    if os.environ.get("FB_DIAGNOSTICS", "").lower() == "true":
        logger.info("=== Diagnostika Facebooku ===")
        return diagnostika()
    logger.info("=== Zdieľanie na Facebook ===")
    db = firestore_client.get_client()
    posli(db)
    logger.info("=== Koniec ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
