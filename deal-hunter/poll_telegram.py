"""
Vyzdvihne stlačené tlačidlá z Telegramu a premietne ich do databázy.

Samostatný vstupný bod, lebo beží na inom takte než hľadanie dealov:
Deal Hunter 3x denne, toto každých 15 minút (telegram-approve.yml).

Spustenie ručne:  python poll_telegram.py
"""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telegram_poll")


def main() -> int:
    import telegram_bot

    if not telegram_bot.is_configured():
        logger.info("Telegram nie je nastavený (chýba token alebo chat ID).")
        return 0

    import firestore_client

    db = firestore_client.get_client()

    if os.environ.get("TELEGRAM_DIAG", "").lower() == "true":
        import json
        logger.info("DIAGNOSTIKA: %s",
                    json.dumps(telegram_bot.diagnose(db), ensure_ascii=False, indent=2))
        return 0

    handled = telegram_bot.process_updates(db)

    if handled:
        logger.info("Spracovaných rozhodnutí: %d", handled)
    else:
        logger.info("Nič nové.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
