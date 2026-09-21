"""
Vyzdvihne stlačené tlačidlá z Telegramu a premietne ich do databázy.

PREČO TO BEŽÍ V SLUČKE
Workflow bol pôvodne naplánovaný každých 15 minút, lenže GitHub tak
časté cron úlohy nedodržiava - v praxi ich púšťal raz za dve až päť
hodín. Schválenie dealu sa tak prejavilo až o niekoľko hodín neskôr.

Namiesto toho beží jeden spustený beh takmer hodinu a používa dlhé
dopytovanie: Telegram podrží spojenie otvorené a odpovie hneď, ako
niekto stlačí tlačidlo. Reakcia je preto v priebehu sekúnd a cron sa
spúšťa raz za hodinu, čo už GitHub dodržiava spoľahlivo.

Spustenie ručne:            python poll_telegram.py
Diagnostika:                TELEGRAM_DIAG=true python poll_telegram.py
"""

import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telegram_poll")

# Ako dlho jeden beh počúva. Necháme rezervu pod hodinovým cronom, aby
# sa dva behy neprekrývali.
DEFAULT_RUN_SECONDS = 3300          # 55 minút
# Ako dlho Telegram podrží jedno spojenie, kým odpovie "nič nové".
LONG_POLL_SECONDS = 25


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

    # POLL_SECONDS chodí z workflowu ako ${{ inputs.seconds }}. Pri
    # spustení cronom nie je žiadny vstup a premenná príde PRÁZDNA, nie
    # nenastavená - int("") by celý beh zhodil skôr, než čokoľvek spraví.
    # Preto sa na chýbajúcu hodnotu nespoliehame a prázdnu aj nezmysel
    # berieme ako "použi predvolené".
    raw_seconds = (os.environ.get("POLL_SECONDS") or "").strip()
    try:
        run_seconds = int(raw_seconds) if raw_seconds else DEFAULT_RUN_SECONDS
    except ValueError:
        logger.warning("POLL_SECONDS nie je číslo, používam %d s.", DEFAULT_RUN_SECONDS)
        run_seconds = DEFAULT_RUN_SECONDS

    if run_seconds <= 0:
        handled = telegram_bot.process_updates(db)
        logger.info("Spracovaných rozhodnutí: %d", handled) if handled else logger.info("Nič nové.")
        return 0

    logger.info("Počúvam %d minút, dlhé dopytovanie po %d s.",
                run_seconds // 60, LONG_POLL_SECONDS)
    deadline = time.monotonic() + run_seconds
    total = 0

    while time.monotonic() < deadline:
        try:
            total += telegram_bot.process_updates(db, long_poll=LONG_POLL_SECONDS)
        except Exception as e:
            # Jedna zlyhaná otázka nesmie ukončiť celý beh - o chvíľu
            # to skúsime znova.
            logger.warning("Dopytovanie zlyhalo, skúšam ďalej: %s", e)
            time.sleep(5)

    logger.info("Koniec behu. Spracovaných rozhodnutí: %d", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
