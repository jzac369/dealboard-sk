"""
Tenká vrstva nad google-cloud-firestore knižnicou.
Používa service account JSON (uložený ako GitHub Secret a za behu
zapísaný do súboru - pozri .github/workflows/deal-hunter.yml).
"""

import logging
from datetime import datetime, timedelta, timezone

from google.cloud import firestore
from google.oauth2 import service_account

import config

logger = logging.getLogger(__name__)


def get_client() -> firestore.Client:
    credentials = service_account.Credentials.from_service_account_file(
        config.FIREBASE_CREDENTIALS_PATH
    )
    return firestore.Client(
        project=config.FIRESTORE_PROJECT_ID, credentials=credentials
    )


def get_recent_source_urls(db: firestore.Client) -> set[str]:
    """
    Vráti množinu sourceUrl hodnôt z už publikovaných dealov za posledných
    N dní (config.DEDUPE_LOOKBACK_DAYS) + zo všetkých aktuálne čakajúcich
    návrhov - aby sme nepridávali duplicity.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.DEDUPE_LOOKBACK_DAYS)
    urls: set[str] = set()

    published = (
        db.collection(config.PUBLISHED_DEALS_COLLECTION)
        .where("createdAt", ">=", cutoff)
        .stream()
    )
    for doc in published:
        data = doc.to_dict()
        if data.get("sourceUrl"):
            urls.add(data["sourceUrl"])

    pending = db.collection(config.PENDING_DEALS_COLLECTION).stream()
    for doc in pending:
        data = doc.to_dict()
        if data.get("sourceUrl"):
            urls.add(data["sourceUrl"])

    return urls


def write_pending_deals(db: firestore.Client, deals: list[dict]) -> int:
    """Zapíše zoznam dealov (ako dict-y) do pending_deals kolekcie. Vráti počet zapísaných."""
    batch = db.batch()
    collection_ref = db.collection(config.PENDING_DEALS_COLLECTION)

    count = 0
    for deal in deals:
        doc_ref = collection_ref.document()
        batch.set(doc_ref, deal)
        count += 1

    if count > 0:
        batch.commit()
        logger.info("Zapísaných %d nových návrhov do %s", count, config.PENDING_DEALS_COLLECTION)

    return count
