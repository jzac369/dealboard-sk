"""
Konfigurácia pre henkukaj.sk Deal Hunter agenta.
Citlivé hodnoty (kľúče) sa načítavajú z premenných prostredia / GitHub Secrets,
nikdy sa nehardcode-ujú priamo v kóde.
"""

import os

# --- Firebase / Firestore ---
# Cesta k JSON súboru so service account credentials.
# V GitHub Actions sa tento súbor vygeneruje za behu zo secretu FIREBASE_SERVICE_ACCOUNT.
FIREBASE_CREDENTIALS_PATH = os.environ.get(
    "FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json"
)
FIRESTORE_PROJECT_ID = os.environ.get("FIRESTORE_PROJECT_ID", "dealboard-e60bf")

# Názov kolekcie, kam sa zapisujú návrhy čakajúce na schválenie
PENDING_DEALS_COLLECTION = "pending_deals"
# Názov kolekcie s už publikovanými dealmi (na deduplikáciu)
PUBLISHED_DEALS_COLLECTION = "deals"

# --- Scraping nastavenia ---
MIN_DEALS_PER_DAY = int(os.environ.get("MIN_DEALS_PER_DAY", "5"))
# Koľko dní dozadu kontrolovať duplicity voči už publikovaným dealom
DEDUPE_LOOKBACK_DAYS = int(os.environ.get("DEDUPE_LOOKBACK_DAYS", "30"))
# Minimálna % zľava, aby sa deal vôbec zvažoval (odfiltruje šum typu -5%)
MIN_DISCOUNT_PERCENT = float(os.environ.get("MIN_DISCOUNT_PERCENT", "15"))

# --- Selenium ---
HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"
PAGE_LOAD_TIMEOUT_SECONDS = 20
REQUEST_DELAY_SECONDS = 1.5  # slušnosť voči scrapovaným stránkam

# --- Notifikácie (voliteľné, Telegram) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
