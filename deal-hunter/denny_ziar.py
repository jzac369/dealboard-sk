"""
Denné pridanie žiaru publikovaným dealom.

NAČO TO JE
Stránka je nová a hlasov je zatiaľ málo. Deal s nulou vyzerá, akoby si
ho nikto ani nevšimol, a návštevník podľa žiaru nevie odlíšiť dobrú
ponuku od slabej. Dovtedy, kým chodia skutoční ľudia, sa každý deň
pridá každému publikovanému dealu 1 až 5 hlasov.

BUĎME SI ÚPRIMNÍ, ČO TO JE
Sú to vymyslené hlasy, nie názor návštevníkov. Preto:
- Dotýka sa len dealov so stavom "approved". Čakajúce ani zamietnuté
  na stránke nie sú a žiar by im bol na nič.
- Starým dealom sa žiar nepridáva. Mesiac stará ponuka, ktorej hlasy
  rastú ďalej, pôsobí falošne - a zároveň by postupne vytlačila nové
  dealy z popredia, lebo náskok by jej rástol každým dňom.
- Pripočítava sa k doterajšej hodnote, takže skutočné hlasy sa
  neprepíšu a poradie medzi nimi sa nezmení.
- Dá sa vypnúť jedným prepínačom v admin zóne, bez zásahu do kódu.
  Až prídu praviedlní návštevníci, treba to vypnúť - inak by ich
  hlasy zanikli v šume.
- Každý beh sa zapíše do denníka zmien, aby sa dalo spätne zistiť,
  koľko zo žiaru je naše a koľko od ľudí.

Nastavenia v settings/moderation:
  dailyHeatBoost       true/false  (predvolene vypnuté)
  dailyHeatMin         predvolene 1
  dailyHeatMax         predvolene 5
  dailyHeatMaxAgeDays  predvolene 30 (0 = bez obmedzenia)

Spúšťa to GitHub Actions (.github/workflows/denny-ziar.yml), raz denne.
"""

from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta, timezone

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

import config
import firestore_client

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("denny_ziar")

# Firestore zvládne 500 zápisov v jednej dávke.
VELKOST_DAVKY = 400


def nastavenia(db) -> dict:
    try:
        return db.document("settings/moderation").get().to_dict() or {}
    except Exception as e:
        logger.error("Nastavenia sa nepodarilo prečítať: %s", e)
        return {}


def je_stary(data: dict, hranica: datetime) -> bool:
    """
    Je deal zverejnený pred hranicou?

    Čas zverejnenia je v "zverejnene", staršie dealy ho ešte nemajú a
    vtedy berieme "timestamp" - ten sa pri schválení prepisuje na čas
    zverejnenia. Keď nie je ani jeden, deal radšej vynecháme: pridávať
    hlasy niečomu, čoho vek nepoznáme, je presne to, čomu sa vyhýbame.
    """
    cas = data.get("zverejnene") or data.get("timestamp")
    if cas is None:
        return True
    try:
        return cas < hranica
    except TypeError:
        return True


def pridaj_ziar(db) -> int:
    nast = nastavenia(db)

    # Predvolene vypnuté. Fabrikovať hlasy je rozhodnutie, ktoré musí
    # niekto urobiť vedome - nie niečo, čo sa zapne samo tým, že sa
    # nasadí nová verzia.
    if nast.get("dailyHeatBoost") is not True:
        logger.info("Denný žiar je vypnutý (settings/moderation → dailyHeatBoost). Končím.")
        return 0

    # Vek dealu rátame od zverejnenia. Nula vypne obmedzenie úplne.
    max_dni = nast.get("dailyHeatMaxAgeDays")
    max_dni = 30 if max_dni is None else max(0, int(max_dni))
    hranica = (datetime.now(timezone.utc) - timedelta(days=max_dni)) if max_dni else None

    najmenej = int(nast.get("dailyHeatMin") or 1)
    najviac = int(nast.get("dailyHeatMax") or 5)
    if najmenej < 0:
        najmenej = 0
    if najviac < najmenej:
        najviac = najmenej

    try:
        dokumenty = list(
            db.collection(config.DEALS_COLLECTION)
            .where(filter=FieldFilter("status", "==", "approved"))
            .stream()
        )
    except Exception as e:
        logger.error("Dealy sa nepodarilo načítať: %s", e)
        return 0

    if not dokumenty:
        logger.info("Žiadne publikované dealy. Končím.")
        return 0

    davka = db.batch()
    v_davke = 0
    upravene = 0
    pridane_spolu = 0

    stare = 0
    for doc in dokumenty:
        data = doc.to_dict() or {}
        if hranica is not None and je_stary(data, hranica):
            stare += 1
            continue
        teraz = data.get("votes") or 0
        pridok = random.randint(najmenej, najviac)
        if pridok == 0:
            continue

        davka.update(doc.reference, {"votes": teraz + pridok})
        pridane_spolu += pridok
        upravene += 1
        v_davke += 1

        if v_davke >= VELKOST_DAVKY:
            davka.commit()
            davka = db.batch()
            v_davke = 0

    if v_davke:
        davka.commit()

    logger.info("Žiar pridaný %d dealom, spolu %d hlasov (rozsah %d-%d). "
                "Vynechaných pre vek: %d.", upravene, pridane_spolu, najmenej, najviac, stare)

    # Zápis do denníka zmien. Bez neho by sa po mesiaci nedalo povedať,
    # ktorá časť žiaru je od ľudí a ktorá od nás.
    try:
        db.collection("audit_log").add({
            "dealId": None,
            "action": "denny-ziar",
            "detail": (f"{upravene} dealov, +{pridane_spolu} hlasov "
                       f"(rozsah {najmenej}-{najviac}, vynechaných pre vek: {stare})"),
            "by": "agent",
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
    except Exception as e:
        logger.warning("Záznam do denníka sa nepodaril: %s", e)

    return upravene


def main() -> int:
    logger.info("=== Denný žiar — %s ===", date.today().isoformat())
    db = firestore_client.get_client()
    pridaj_ziar(db)
    logger.info("=== Koniec ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
