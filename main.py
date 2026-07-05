"""
Deal Hunter - hlavný vstupný bod.

Postup:
1. Spustí všetky scrapery zo scrapers/__init__.py -> ALL_SCRAPERS
2. Odfiltruje kandidátov pod MIN_DISCOUNT_PERCENT
3. Odstráni duplicity voči už publikovaným/čakajúcim dealom (podľa sourceUrl)
4. Zoradí zostupne podľa % zľavy
5. Zapíše TOP N (min. config.MIN_DEALS_PER_DAY) do Firestore pending_deals
6. (voliteľne) pošle Telegram notifikáciu, že čakajú na schválenie

Spúšťa sa denne cez GitHub Actions (.github/workflows/deal-hunter.yml).
"""

import logging
import sys

import config
import firestore_client
from scrapers import ALL_SCRAPERS
from scrapers.base import DealCandidate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("deal_hunter")


def run_all_scrapers() -> list[DealCandidate]:
    all_candidates: list[DealCandidate] = []

    for scraper_cls in ALL_SCRAPERS:
        scraper = scraper_cls()
        logger.info("Spúšťam scraper: %s", scraper.source_name)
        try:
            found = scraper.fetch_candidates()
            logger.info("%s: nájdených %d kandidátov", scraper.source_name, len(found))
            all_candidates.extend(found)
        except Exception as e:
            # Jeden padnutý zdroj nesmie zhodiť celý denný beh
            logger.error("Scraper %s zlyhal: %s", scraper.source_name, e, exc_info=True)

    return all_candidates


def filter_and_rank(
    candidates: list[DealCandidate], already_seen_urls: set[str]
) -> list[DealCandidate]:
    filtered = [
        c
        for c in candidates
        if c.discount_percent >= config.MIN_DISCOUNT_PERCENT
        and c.source_url not in already_seen_urls
    ]

    # deduplikácia v rámci tohto behu (rôzne zdroje môžu nájsť ten istý produkt)
    seen_in_run = set()
    unique = []
    for c in filtered:
        if c.source_url in seen_in_run:
            continue
        seen_in_run.add(c.source_url)
        unique.append(c)

    unique.sort(key=lambda c: c.discount_percent, reverse=True)
    return unique


def notify_telegram(count: int) -> None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    import requests

    text = f"🛍️ Deal Hunter: pridaných {count} nových návrhov, čakajú na schválenie v admin paneli."
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        logger.warning("Telegram notifikácia zlyhala: %s", e)


def main() -> int:
    logger.info("=== Deal Hunter - denný beh ===")

    db = firestore_client.get_client()
    already_seen = firestore_client.get_recent_source_urls(db)
    logger.info("Existujúcich URL na deduplikáciu: %d", len(already_seen))

    raw_candidates = run_all_scrapers()
    logger.info("Spolu nájdených kandidátov zo všetkých zdrojov: %d", len(raw_candidates))

    ranked = filter_and_rank(raw_candidates, already_seen)
    logger.info("Po filtrovaní a deduplikácii ostalo: %d", len(ranked))

    if len(ranked) < config.MIN_DEALS_PER_DAY:
        logger.warning(
            "Nájdených len %d dealov, menej než požadovaných %d. "
            "Zapisujem, čo sa našlo.",
            len(ranked),
            config.MIN_DEALS_PER_DAY,
        )

    top_deals = ranked[: max(config.MIN_DEALS_PER_DAY, 10)]
    deal_dicts = [d.to_firestore_dict() for d in top_deals]

    written = firestore_client.write_pending_deals(db, deal_dicts)
    notify_telegram(written)

    logger.info("=== Hotovo. Zapísaných %d návrhov. ===", written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
