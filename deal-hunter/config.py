"""
Konfigurácia Deal Hunter agenta pre henkukaj.sk.

Citlivé hodnoty (kľúče, tokeny) sa načítavajú z premenných prostredia
(GitHub Secrets) — nikdy sa nezapisujú priamo do kódu ani do repozitára.
"""

import os


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_list(name: str) -> list[str]:
    """Načíta zoznam oddelený čiarkami z premennej prostredia."""
    raw = os.environ.get(name, "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


# ── Firebase / Firestore ──────────────────────────────────────────────
FIREBASE_CREDENTIALS_PATH = os.environ.get(
    "FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json"
)
FIRESTORE_PROJECT_ID = os.environ.get("FIRESTORE_PROJECT_ID", "dealboard-e60bf")

# POZOR: agent zapisuje do TEJ ISTEJ kolekcie, ktorú číta admin panel,
# len so statusom "pending". Vlastná kolekcia (napr. pending_deals) by
# znamenala, že návrhy v admin paneli nikdy neuvidíš.
DEALS_COLLECTION = "deals"

# Mená, pod ktorými sa návrhy agenta zobrazia v poli "autor".
# Vyberá sa z nich náhodne, aby zoznam nevyzeral ako jeden robot.
# Koncovka ".DH" je zámerná: podľa nej sa dá kedykoľvek zistiť, že
# deal nepridal človek, ale agent.
# Bez emoji - stránka ich v menách autorov nepoužíva a na každom
# systéme sa kreslia inak.
AGENT_AUTHOR_NAMES = _env_list("AGENT_AUTHOR_NAMES") or [
    "karci773.DH", "roseHIP.DH", "srlak007.DH", "miso71421.DH", "savancek7.DH",
]
AGENT_AUTHOR_NAME = os.environ.get("AGENT_AUTHOR_NAME") or AGENT_AUTHOR_NAMES[0]


def meno_autora() -> str:
    """Náhodné meno zo zoznamu - volá sa pre každý návrh zvlášť."""
    import random
    return random.choice(AGENT_AUTHOR_NAMES)


# ── Výber a filtrovanie dealov ────────────────────────────────────────
# Minimálna zľava v %, aby sa deal vôbec zvažoval (odfiltruje šum typu -5 %).
MIN_DISCOUNT_PERCENT = _env_float("MIN_DISCOUNT_PERCENT", 25)
# Maximálna zľava — nad touto hranicou to býva chyba v dátach, nie deal.
MAX_DISCOUNT_PERCENT = _env_float("MAX_DISCOUNT_PERCENT", 95)
# Minimálna cena v €. Odfiltruje šum typu "zľava 50 %" na položke za 20 centov.
# Nízka hranica je zámer: pri potravinách je aj minerálka za 0,55 € reálny deal.
# Pod pätnásť eur sú v letákoch prevažne jogurty, omáčky a ovocie.
# Zľava 50 % na Actimel za 1,29 € je síce zľava, ale nie deal - a presne
# takéto návrhy sa zamietali. Kategóriový filter ich nechytí všetky,
# lebo odhad kategórie podľa názvu ich zaradí medzi "Iné".
MIN_DEAL_PRICE = _env_float("MIN_DEAL_PRICE", 15.0)
# Koľko návrhov maximálne zapísať za jeden beh.
# Dva behy denne (ráno a večer) dávajú 10 návrhov na deň.
MAX_DEALS_PER_RUN = _env_int("MAX_DEALS_PER_RUN", 5)

# Tvrdý denný strop. Je to poistka, nie bežný limit: 5. 10. 2026 sa
# plánovač kvôli vyčerpanej kvóte Firestore reštartoval každých 5 minút,
# spustil agenta zakaždým znova a za deň prišlo vyše 230 návrhov. Tento
# strop to zastaví aj vtedy, keď sa taká slučka zopakuje.
MAX_DEALS_PER_DAY = _env_int("MAX_DEALS_PER_DAY", 10)
# Nezverejňovať deal, ku ktorému nevieme zostaviť odkaz na predajcu.
# Bez toho by sa do sveta dostal odkaz na zdroj (zlacnene.sk), teda na
# cudziu stránku. Radšej deal vynechať; obchod sa doplní do tabuľky
# v merchant_links.py alebo cez admin panel a nabudúce prejde.
REQUIRE_KNOWN_MERCHANT = os.environ.get("REQUIRE_KNOWN_MERCHANT", "true").lower() == "true"

# Najviac dealov z jedného obchodu za beh - aby výber nevyzeral
# ako leták jediného reťazca.
MAX_PER_STORE = _env_int("MAX_PER_STORE", 4)
# Koľko bodov zľavy stráca obchod za každý deal, ktorý už dnes navrhol
# (alebo ktorý už bol vybraný v tomto behu). 15 znamená, že obchod s o 15
# bodov menšou zľavou predbehne ten, z ktorého dnes už niečo bolo.
STORE_REPEAT_PENALTY = _env_float("STORE_REPEAT_PENALTY", 15)
# Najviac dealov z jednej kategórie za beh. Bez tohto by potraviny
# obsadili celý výber - letáky reťazcov sú prevažne potravinové.
MAX_PER_CATEGORY = _env_int("MAX_PER_CATEGORY", 3)
# Koľko dní dozadu sa pozerať pri kontrole duplicít.
DEDUPE_LOOKBACK_DAYS = _env_int("DEDUPE_LOOKBACK_DAYS", 10)
# Ten istý produkt sa znova navrhne najskôr po toľkých dňoch. Zverejnený
# deal nemá zmysel ponúkať znova hneď a zamietnutý už vôbec - preto má
# zamietnutie dlhšiu lehotu.
DEDUPE_APPROVED_DAYS = _env_int("DEDUPE_APPROVED_DAYS", 7)
DEDUPE_REJECTED_DAYS = _env_int("DEDUPE_REJECTED_DAYS", 10)


# ── Zdroje ────────────────────────────────────────────────────────────
# Zapnuté scrapery. Názvy zodpovedajú kľúčom v scrapers/__init__.py.
ENABLED_SCRAPERS = _env_list("ENABLED_SCRAPERS") or ["zlacnene", "feeds", "shop_feeds"]

# Slová v názve, pri ktorých položku vôbec nezvažujeme. Zámerne krátky
# zoznam: "tester" tu napríklad nie je, lebo by vyradil aj tester batérií.
EXCLUDED_TITLE_WORDS = _env_list("EXCLUDED_TITLE_WORDS") or ["vzorka", "vzorky", "sample"]

# Kategórie, ktoré sa na stránku nedostanú vôbec. Predvolene žiadna.
BLOCKED_CATEGORIES = _env_list("BLOCKED_CATEGORIES")

# Kategórie, ktoré smú tvoriť len obmedzený podiel jedného behu, a aký.
# Potraviny sú tu preto, že ich zdroj nájde najviac (letáky reťazcov sú
# prevažne potravinové) a bez stropu by zaplnili celý výber - presne to
# sa dialo a väčšina takých návrhov končila zamietnutím. Strop ich
# nezakazuje, len im nedovolí prevalcovať elektroniku a ostatné.
CAPPED_CATEGORIES = _env_list("CAPPED_CATEGORIES") or ["Jedlo & Nápoje"]
CAPPED_CATEGORY_SHARE = _env_float("CAPPED_CATEGORY_SHARE", 0.2)

# Koľko strán všeobecného zoznamu prejsť na zlacnene.sk (20 položiek na stranu).
ZLACNENE_MAX_PAGES = _env_int("ZLACNENE_MAX_PAGES", 2)
# Ktoré kategórie sťahovať. Prázdne = všetky z CATEGORY_MAP
# v scrapers/zlacnene.py. Napr: ZLACNENE_CATEGORIES="naradie,hracky"
ZLACNENE_CATEGORIES = _env_list("ZLACNENE_CATEGORIES")

# Affiliate produktové feedy (Dognet a pod.) — URL oddelené čiarkami.
# Napr: FEED_URLS="https://partner1.sk/feed.xml,https://partner2.sk/heureka.xml"
FEED_URLS = _env_list("FEED_URLS")
# Šablóna partnerského odkazu, napr.
#   AFFILIATE_LINK_TEMPLATE="https://go.dognet.sk/?a_aid=TVOJE_ID&desturl={url}"
# Použije sa len na odkazy z feedov, ktoré tracking ešte nemajú.
# Patrí do secrets - je v nej tvoje partnerské ID.
AFFILIATE_LINK_TEMPLATE = os.environ.get("AFFILIATE_LINK_TEMPLATE", "")

# O koľko % musí cena spadnúť pod doteraz najnižšiu videnú, aby sa
# položka z feedu zverejnila. Feedy pôvodnú cenu neuvádzajú, takže
# zľavu určujeme vlastným meraním, nie tvrdením predajcu.
FEED_MIN_DROP_PERCENT = _env_float("FEED_MIN_DROP_PERCENT", 20)

# Vypíše štruktúru feedov do logu (bez citlivých údajov) a skončí.
FEED_DIAGNOSTICS = os.environ.get("FEED_DIAGNOSTICS", "false").lower() == "true"

# Koľko položiek maximálne načítať z jedného feedu (feedy bývajú obrovské).
# Strop na počet položiek z jedného feedu. Zvýšené z 5 000: feed
# GymBeamu má 9 522 položiek a pri starom strope sa polovica ani
# nepozrela - pritom sa neberie najlepších 5 000, ale prvých 5 000
# v poradí, v akom ich feed uvádza. To je náhodný výber, nie výber.
FEED_MAX_ITEMS = _env_int("FEED_MAX_ITEMS", 25000)

# Koľko položiek najviac pošleme do sledovania cien z jedného feedu,
# ktorý zľavy sám neuvádza. Vedierka price_watch majú kapacitu rádovo
# 216 000 produktov (limit 1 MiB na dokument ÷ ~97 B na záznam × 20);
# pri desiatich takých feedoch zostane polovica rezervou.
FEED_WATCH_MAX = _env_int("FEED_WATCH_MAX", 10000)

# Keď je vo feede "v akcii" väčší podiel sortimentu, prečiarknutej cene
# neveríme. Pri 50 %: GymBeam (45 %, naozaj robí veľa akcií) prejde,
# 4Home (81 %, trvalo prečiarknuté ceny) nie.
FEED_MAX_SALE_SHARE = _env_float("FEED_MAX_SALE_SHARE", 0.5)


# ── HTTP slušnosť ─────────────────────────────────────────────────────
USER_AGENT = os.environ.get(
    "USER_AGENT",
    "HenKukajDealHunter/1.0 (+https://henkukaj.sk; kontakt: info@henkukaj.sk)",
)
# ── Hľadanie na webe (Claude + vyhľadávanie), pozri scrapers/web_hunt.py ──
# Zdroj "web_hunt" sa zapína v admine (Agent -> zdroje) a potrebuje secret
# ANTHROPIC_API_KEY. Každý beh stojí peniaze, preto najviac raz za interval.
WEB_HUNT_MODEL = os.environ.get("WEB_HUNT_MODEL", "claude-opus-5-5")
WEB_HUNT_INTERVAL_HOURS = _env_int("WEB_HUNT_INTERVAL_HOURS", 20)
WEB_HUNT_MAX_VYHLADAVANI = _env_int("WEB_HUNT_MAX_VYHLADAVANI", 12)
WEB_HUNT_MAX_NAVRHOV = _env_int("WEB_HUNT_MAX_NAVRHOV", 20)
WEB_HUNT_SKUPINY = _env_list("WEB_HUNT_SKUPINY") or [
    "technológie a gaming", "domácnosť a záhrada", "deti a rodina", "kozmetika a starostlivosť",
    "šport a outdoor", "cestovanie", "móda", "knihy a vzdelávanie", "jedlo a nápoje",
    "auto-moto", "domáce zvieratá", "softvér a predplatné",
]

REQUEST_TIMEOUT_SECONDS = _env_int("REQUEST_TIMEOUT_SECONDS", 25)
# Pauza medzi requestmi na ten istý web. zlacnene.sk v robots.txt
# žiada Crawl-delay: 1 — držíme sa toho s rezervou.
CRAWL_DELAY_SECONDS = _env_float("CRAWL_DELAY_SECONDS", 1.5)
HTTP_MAX_RETRIES = _env_int("HTTP_MAX_RETRIES", 3)


# ── Notifikácie (voliteľné) ───────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Náhodný štartovací žiar (stupne) pre nové dealy.
#
# ZÁMERNE VYPNUTÉ (0-0). Je to jednorazová pomôcka na rozbeh stránky, aby
# nepôsobila mŕtvo, kým sa nenazbierajú skutočné hlasy. Plánované behy ho
# nikdy nezapínajú - workflow ho posiela len pri ručnom spustení. Trvalé
# používanie by návštevníkom tvrdilo, že deal ohodnotili ľudia, čo by
# nebola pravda.
VOTE_BOOST_MIN = _env_int("VOTE_BOOST_MIN", 0)
VOTE_BOOST_MAX = _env_int("VOTE_BOOST_MAX", 0)

# Jednorazový čistý štart: zmaže neschválené návrhy od agenta a jeho
# pamäť, potom beží normálne ďalej. Schválených dealov sa nedotkne.
RESET_PENDING = os.environ.get("RESET_PENDING", "false").lower() == "true"

# Štartovací žiar pre zľavové kódy. Rovnako ako pri dealoch: zámerne
# vypnuté a plánované behy to nikdy nezapnú.
# Časť kódov dostane zápornú hodnotu - zoznam, kde má všetko kladné
# číslo, pôsobí nedôveryhodne, a pri kupónoch je bežné, že časť
# nefunguje.
COUPON_BOOST_MIN = _env_int("COUPON_BOOST_MIN", 0)
COUPON_BOOST_MAX = _env_int("COUPON_BOOST_MAX", 0)
COUPON_FREEZE_CHANCE = _env_float("COUPON_FREEZE_CHANCE", 0.18)
COUPON_FREEZE_MIN = _env_int("COUPON_FREEZE_MIN", -9)
COUPON_FREEZE_MAX = _env_int("COUPON_FREEZE_MAX", -2)

# Jednorazová oprava: prepíše odkazy starých dealov zo zdroja na predajcu.
FIX_URLS = os.environ.get("FIX_URLS", "false").lower() == "true"

# Nezapisovať do Firestore, len vypísať, čo by sa zapísalo.
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


# ── Nastavenia z admin zóny (settings/agent) ──────────────────────────
# Hodnoty vyššie sú predvolené. Admin ich vie prepísať bez zásahu do
# kódu; agent si ich načíta na začiatku každého behu. Každá hodnota sa
# overí - nezmysel z admina (záporná cena, prázdny zoznam zdrojov) sa
# ignoruje a ostane predvolená, aby agent nezastal.
_CISLA = {
    # kľúč v admine: (premenná, min, max)
    "minZlava": ("MIN_DISCOUNT_PERCENT", 0, 95),
    "maxZlava": ("MAX_DISCOUNT_PERCENT", 5, 100),
    "minCena": ("MIN_DEAL_PRICE", 0, 100000),
    "maxNaBeh": ("MAX_DEALS_PER_RUN", 1, 50),
    "maxNaDen": ("MAX_DEALS_PER_DAY", 1, 100),
    "znovaPoDnochZverejnene": ("DEDUPE_APPROVED_DAYS", 1, 365),
    "znovaPoDnochZamietnute": ("DEDUPE_REJECTED_DAYS", 1, 365),
    "maxNaObchod": ("MAX_PER_STORE", 1, 50),
    "penalizaciaObchodu": ("STORE_REPEAT_PENALTY", 0, 100),
    "maxNaKategoriu": ("MAX_PER_CATEGORY", 1, 50),
    "podielObmedzenych": ("CAPPED_CATEGORY_SHARE", 0, 1),
    "feedMinPokles": ("FEED_MIN_DROP_PERCENT", 0, 95),
}
_ZOZNAMY = {
    "obmedzeneKategorie": "CAPPED_CATEGORIES",
    "blokovaneKategorie": "BLOCKED_CATEGORIES",
    "vylucenaSlova": "EXCLUDED_TITLE_WORDS",
}
PREDVOLENE = {k: globals()[v[0]] for k, v in _CISLA.items()}
PREDVOLENE.update({k: list(globals()[v]) for k, v in _ZOZNAMY.items()})
PREDVOLENE["zdroje"] = list(ENABLED_SCRAPERS)


def pouzi_nastavenia(data: dict) -> list[str]:
    """Prepíše hodnoty podľa admina. Vráti zoznam zmenených (do logu)."""
    import logging
    from urllib.parse import urlparse

    g = globals()
    zmenene = []
    for kluc, (premenna, dole, hore) in _CISLA.items():
        v = data.get(kluc)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and dole <= v <= hore:
            g[premenna] = int(v) if isinstance(g[premenna], int) else float(v)
            zmenene.append(f"{premenna}={g[premenna]}")
    for kluc, premenna in _ZOZNAMY.items():
        v = data.get(kluc)
        if isinstance(v, list) and all(isinstance(x, str) for x in v):
            g[premenna] = [x.strip() for x in v if x.strip()][:50]
            zmenene.append(f"{premenna}={g[premenna]}")
    zdroje = data.get("zdroje")
    if isinstance(zdroje, list) and zdroje:
        g["ENABLED_SCRAPERS"] = [str(x) for x in zdroje]
        zmenene.append(f"ENABLED_SCRAPERS={g['ENABLED_SCRAPERS']}")
    vypnute = data.get("vypnuteFeedy")
    if isinstance(vypnute, list) and vypnute:
        pred = len(FEED_URLS)
        g["FEED_URLS"] = [u for u in FEED_URLS
                          if (urlparse(u).hostname or "").replace("www.", "") not in vypnute]
        zmenene.append(f"vypnutých feedov: {pred - len(g['FEED_URLS'])}")
    if zmenene:
        logging.getLogger("config").info("Nastavenia z admina: %s", "; ".join(zmenene))
    return zmenene


# Feedy pridané v admine (nastavenia_admin/feedy). Sú oddelené od
# FEED_URLS zámerne: adresa feedu z Dognetu obsahuje partnerské ID, a to
# nepatrí do settings/{...}, ktoré číta aj verejná stránka. Tento dokument
# vidí len admin a agent cez service account.
NAZVY_OBCHODOV: dict[str, str] = {}


def pouzi_feedy(data: dict) -> int:
    """Pridá feedy z admina k tým z premennej FEED_URLS. Vráti ich počet."""
    import logging
    from urllib.parse import urlparse

    zoznam = data.get("feedy")
    if not isinstance(zoznam, list):
        return 0
    pridane = []
    for f in zoznam:
        if not isinstance(f, dict) or not f.get("zap", True):
            continue
        url = str(f.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        # Ten istý feed môže byť aj v tajomstve FEED_URLS - dvakrát
        # načítaný by dal každý produkt dvakrát.
        if url in FEED_URLS or url in pridane:
            continue
        pridane.append(url)
        nazov = str(f.get("nazov") or "").strip()
        domena = str(f.get("domena") or "").strip().lower().replace("www.", "")
        if nazov and domena:
            NAZVY_OBCHODOV[domena] = nazov[:40]
    if pridane:
        globals()["FEED_URLS"] = list(FEED_URLS) + pridane
        logging.getLogger("config").info("Feedy z admina: %d", len(pridane))
    return len(pridane)


def info_pre_admin() -> dict:
    """Čo admin potrebuje na zobrazenie volieb: dostupné zdroje, feedy
    (len doména - celá adresa obsahuje partnerské ID a patrí do secrets)
    a predvolené hodnoty."""
    from urllib.parse import urlparse

    from models import VALID_CATEGORIES
    from scrapers import AVAILABLE_SCRAPERS

    return {
        "zdroje": sorted(AVAILABLE_SCRAPERS.keys()),
        "feedy": sorted({(urlparse(u).hostname or "").replace("www.", "") for u in FEED_URLS} - {""}),
        "kategorie": list(VALID_CATEGORIES),
        "predvolene": PREDVOLENE,
    }
