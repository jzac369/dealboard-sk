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
AGENT_AUTHOR_NAME = os.environ.get("AGENT_AUTHOR_NAME", "Deal Hunter 🤖")


# ── Výber a filtrovanie dealov ────────────────────────────────────────
# Minimálna zľava v %, aby sa deal vôbec zvažoval (odfiltruje šum typu -5 %).
MIN_DISCOUNT_PERCENT = _env_float("MIN_DISCOUNT_PERCENT", 25)
# Maximálna zľava — nad touto hranicou to býva chyba v dátach, nie deal.
MAX_DISCOUNT_PERCENT = _env_float("MAX_DISCOUNT_PERCENT", 95)
# Minimálna cena v €. Odfiltruje šum typu "zľava 50 %" na položke za 20 centov.
# Nízka hranica je zámer: pri potravinách je aj minerálka za 0,55 € reálny deal.
MIN_DEAL_PRICE = _env_float("MIN_DEAL_PRICE", 0.50)
# Koľko návrhov maximálne zapísať za jeden beh (aby ťa schvaľovanie nezahltilo).
MAX_DEALS_PER_RUN = _env_int("MAX_DEALS_PER_RUN", 12)
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
ENABLED_SCRAPERS = _env_list("ENABLED_SCRAPERS") or ["zlacnene", "feeds"]

# Koľko strán všeobecného zoznamu prejsť na zlacnene.sk (20 položiek na stranu).
ZLACNENE_MAX_PAGES = _env_int("ZLACNENE_MAX_PAGES", 2)
# Ktoré kategórie sťahovať. Prázdne = všetky z CATEGORY_MAP
# v scrapers/zlacnene.py. Napr: ZLACNENE_CATEGORIES="naradie,hracky"
ZLACNENE_CATEGORIES = _env_list("ZLACNENE_CATEGORIES")

# Affiliate produktové feedy (Dognet a pod.) — URL oddelené čiarkami.
# Napr: FEED_URLS="https://partner1.sk/feed.xml,https://partner2.sk/heureka.xml"
FEED_URLS = _env_list("FEED_URLS")
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

# Nezapisovať do Firestore, len vypísať, čo by sa zapísalo.
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
