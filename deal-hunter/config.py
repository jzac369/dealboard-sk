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

# Meno, pod ktorým sa návrhy zobrazia v poli "autor".
# Bez emoji zámerne - stránka ich v menách autorov nepoužíva a
# na každom systéme sa kreslia inak.
AGENT_AUTHOR_NAME = os.environ.get("AGENT_AUTHOR_NAME", "Deal Hunter")


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
# Pri 3 behoch denne to dáva denný strop 30 návrhov na schválenie.
MAX_DEALS_PER_RUN = _env_int("MAX_DEALS_PER_RUN", 10)
# Nezverejňovať deal, ku ktorému nevieme zostaviť odkaz na predajcu.
# Bez toho by sa do sveta dostal odkaz na zdroj (zlacnene.sk), teda na
# cudziu stránku. Radšej deal vynechať; obchod sa doplní do tabuľky
# v merchant_links.py alebo cez admin panel a nabudúce prejde.
REQUIRE_KNOWN_MERCHANT = os.environ.get("REQUIRE_KNOWN_MERCHANT", "true").lower() == "true"

# Najviac dealov z jedného obchodu za beh - aby výber nevyzeral
# ako leták jediného reťazca.
MAX_PER_STORE = _env_int("MAX_PER_STORE", 4)
# Najviac dealov z jednej kategórie za beh. Bez tohto by potraviny
# obsadili celý výber - letáky reťazcov sú prevažne potravinové.
MAX_PER_CATEGORY = _env_int("MAX_PER_CATEGORY", 3)
# Koľko dní dozadu sa pozerať pri kontrole duplicít.
DEDUPE_LOOKBACK_DAYS = _env_int("DEDUPE_LOOKBACK_DAYS", 30)


# ── Zdroje ────────────────────────────────────────────────────────────
# Zapnuté scrapery. Názvy zodpovedajú kľúčom v scrapers/__init__.py.
ENABLED_SCRAPERS = _env_list("ENABLED_SCRAPERS") or ["zlacnene", "feeds", "shop_feeds"]

# Kategórie, ktoré sa na stránku nedostanú, nech ich zdroj nájde koľko chce.
# Potraviny sem patria zámerne: tvorili väčšinu návrhov agenta a takmer
# všetky sa zamietali. Ceny základných potravín má stránka vo vlastnej
# sekcii z národného porovnávača - tam dávajú zmysel, ako deal nie.
BLOCKED_CATEGORIES = _env_list("BLOCKED_CATEGORIES") or ["Jedlo & Nápoje"]

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
FEED_MAX_ITEMS = _env_int("FEED_MAX_ITEMS", 5000)


# ── HTTP slušnosť ─────────────────────────────────────────────────────
USER_AGENT = os.environ.get(
    "USER_AGENT",
    "HenKukajDealHunter/1.0 (+https://henkukaj.sk; kontakt: info@henkukaj.sk)",
)
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
