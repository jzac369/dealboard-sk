"""
Stiahne dnešné ceny základných potravín a zapíše ich do databázy.

PREČO SAMOSTATNÝ SKRIPT A NIE SÚČASŤ AGENTA
Národný porovnávač cenyslovensko.sk odpovedá len zo slovenských adries.
Z GitHub Actions každé volanie vyprší (overené: api.cenyslovensko.sk má
jedinú IPv4 adresu a spojenie sa nikdy nenadviaže). Agent v cloude teda
ceny stiahnuť nevie a táto jedna úloha musí bežať tu, na domácom
počítači, raz denne.

Zvyšok agenta zostáva v cloude — je to len táto jedna vec.

Spustenie:   python refresh_food_prices.py
Bez zápisu:  python refresh_food_prices.py --skuska
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("food")


def main() -> int:
    dry_run = "--skuska" in sys.argv or "--dry-run" in sys.argv

    import food_prices

    try:
        snapshot = food_prices.build_snapshot()
    except Exception as e:
        logger.error("Ceny sa nepodarilo stiahnuť: %s", e)
        return 1

    items = snapshot.get("items") or []
    baskets = snapshot.get("baskets") or []

    if not items:
        # Prázdny výsledok radšej nezapisovať — prepísal by posledné
        # funkčné ceny prázdnotou a sekcia na stránke by osirela.
        logger.error("Porovnávač nevrátil ani jednu položku, nezapisujem.")
        return 1

    logger.info("Dátum prehľadu: %s, položiek: %d", snapshot.get("reportDate"), len(items))
    for basket in baskets:
        logger.info("  %-12s %6.2f EUR", basket.get("vendor"), basket.get("total", 0))

    if dry_run:
        logger.info("Skúšobný beh — do databázy sa nezapisuje.")
        return 0

    import firestore_client

    db = firestore_client.get_client()
    if firestore_client.refresh_food_prices(db):
        logger.info("Hotovo, ceny sú na stránke.")
        return 0

    logger.error("Zápis do databázy zlyhal.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
