"""
Jednorazový import zľavových kódov z Dognetu.

Zoznam je prepísaný z prehľadu kupónov v Dognete. Keď raz dostaneme
prístup k ich JSON feedu, toto sa nahradí automatickým sťahovaním a
súbor sa zmaže.

Kódy, ktoré na stránke už sú, preskakujeme - porovnávame podľa kódu aj
obchodu, lebo ten istý kód môže patriť dvom e-shopom (TNX50TYB5 má
Luxusne-holenie aj Luxusne-pera).

Spustenie:  python import_dognet_coupons.py
Len výpis:  python import_dognet_coupons.py --skuska
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("dognet")

# (obchod, doména, kód, zľava, popis, platí_do)
# Zľavu píšeme v tvare, aký používa stránka: "Zľava 20 %", "Zľava 5 €",
# "Doprava zdarma" - inak by zoznam vyzeral rozhádzane.
KUPONY = [
    ("Lidl.sk", "lidl.sk", "SHIP", "Doprava zdarma", "", "2026-09-23"),
    ("Sportby.sk", "sportby.sk", "ex10", "Zľava 10 %",
     "Extra zľava aj na zľavnený tovar. Platí na lyže, lyžiarky, lyžiarske oblečenie, snowboard, bežky a iné.", None),
    ("Feelpearls.sk", "feelpearls.sk", "PERLY20", "Zľava 20 %", "", "2026-12-31"),
    ("Cropp.com", "cropp.com", "CROPP30", "Zľava 30 %", "", None),
    ("Lumories.sk", "lumories.sk", "SKP-DISCOUNT13", "Zľava 13 %",
     "Pre prihlásených firemných zákazníkov pri objednávke od 149 €.", None),
    ("Stoporex.sk", "stoporex.sk", "zlava5", "Zľava 5 %", "", None),
    ("Dizajnove-doplnky.sk", "dizajnove-doplnky.sk", "dizajnove5", "Zľava 5 %", "", None),
    ("69shop.sk", "69shop.sk", "69shop", "Zľava 5 %", "", None),
    ("69shop.sk", "69shop.sk", "DLXH7L96", "Zľava 6 %", "", None),
    ("Sparkl.sk", "sparkl.sk", "sparkldog10", "Zľava 10 %", "Na všetko.", None),
    ("Autovybava.sk", "autovybava.sk", "DOGNET", "Zľava 2 €", "Pri nákupe nad 20 €.", None),
    ("Avita.sk", "avita.sk", "DOGNET15", "Zľava 15 %",
     "Platí na celú objednávku okrem zľavnených produktov.", None),
    ("Boel.sk", "boel.sk", "BOELX5B9", "Zľava 3 %", "", None),
    ("Pobalsa.sk", "pobalsa.sk", "dognet2", "Zľava 2 €", "Pri objednávke nad 30 €.", None),
    ("Pobalsa.sk", "pobalsa.sk", "dognet3", "Zľava 3 €", "Pri objednávke nad 50 €.", None),
    ("Pobalsa.sk", "pobalsa.sk", "dognet5", "Zľava 5 €", "Pri objednávke nad 100 €.", None),
    ("Pobalsa.sk", "pobalsa.sk", "dognet10", "Zľava 10 €", "Pri objednávke nad 200 €.", None),
    ("nabbi.sk", "nabbi.sk", "NABBI3PAF1", "Zľava 3 %", "", None),
    ("Milinko-oblecenie.sk", "milinko-oblecenie.sk", "dgmodal5", "Zľava 15 %", "Na všetok sortiment.", None),
    ("Milinko-oblecenie.sk", "milinko-oblecenie.sk", "dgm189", "Zľava 10 %",
     "Platí na celú objednávku okrem zľavnených produktov.", None),
    ("Dekoria.sk", "dekoria.sk", "zavesy10", "Zľava 10 %", "Na závesy na mieru.", "2026-12-31"),
    ("Dekoria.sk", "dekoria.sk", "rimskerolety10", "Zľava 10 %", "Na rímske rolety na mieru.", "2026-12-31"),
    ("Dekoria.sk", "dekoria.sk", "zaclony10", "Zľava 10 %", "Na záclony na mieru.", "2026-12-31"),
    ("Dekoria.sk", "dekoria.sk", "prehozy10", "Zľava 10 %", "Na prehozy na mieru.", "2026-12-31"),
    ("Dekoria.sk", "dekoria.sk", "obrusy10", "Zľava 10 %", "Na obrusy na mieru.", "2026-12-31"),
    ("Dekoria.sk", "dekoria.sk", "dekoracie8", "Zľava 8 %", "Na dekorácie.", "2026-12-31"),
    ("Neurinu.sk", "neurinu.sk", "HAPPY5", "Zľava 5 %",
     "Z ceny objednávky. Kupón sa dá využiť len raz.", None),
    ("Inpostele.sk", "inpostele.sk", "IZBA05", "Zľava 5 %", "Na kategóriu Obývacia izba.", None),
    ("Coffeein.sk", "coffeein.sk", "coffeedg", "Zľava 5 %", "", None),
    ("IronAesthetics.sk", "ironaesthetics.sk", "IRON20", "Zľava 20 €", "Na nákup nad 200 €.", None),
    ("IronAesthetics.sk", "ironaesthetics.sk", "IRON15", "Zľava 15 €", "Na nákup nad 150 €.", None),
    ("IronAesthetics.sk", "ironaesthetics.sk", "IRON10", "Zľava 10 €", "Na nákup nad 100 €.", None),
    ("IronAesthetics.sk", "ironaesthetics.sk", "IRON5", "Zľava 5 €", "Na nákup nad 50 €.", None),
    ("Solapoint.sk", "solapoint.sk", "DNNSDU", "Zľava 5 %", "Na všetky produkty bez obmedzenia.", None),
    ("Dekoraciedobytu.sk", "dekoraciedobytu.sk", "facebook", "Zľava 5 %", "Dodatočná zľava pri objednávke.", None),
    ("KampotskeKorenie.sk", "kampotskekorenie.sk", "DOPRAVAZADARMO", "Doprava zdarma",
     "Doprava zdarma nad 1000 Kč na všetko.", None),
    ("Stressfix.sk", "stressfix.sk", "bezstresu", "Zľava 10 %", "Z celej objednávky.", None),
    ("Supershape.sk", "supershape.sk", "DN10", "Zľava 10 %", "", None),
    ("Luxusne-holenie.sk", "luxusne-holenie.sk", "TNX50TYB5", "Zľava 2 %", "Platí na všetko.", None),
    ("Luxusne-pera.sk", "luxusne-pera.sk", "TNX50TYB5", "Zľava 2 %", "Platí na všetko.", None),
    ("Vejare.sk", "vejare.sk", "zlava10", "Zľava 10 %", "Na všetko.", None),
    ("AJprodukty.sk", "ajprodukty.sk", "POL5", "Zľava 5 %", "", None),
    ("AJprodukty.sk", "ajprodukty.sk", "DSA3", "Zľava 3 %", "", None),
    ("AJprodukty.sk", "ajprodukty.sk", "QWE2", "Zľava 2 %", "", None),
    ("Incacollagen.sk", "incacollagen.sk", "CHCEMZLAVU", "Zľava 5 €", "", None),
    ("Bohatstvo-Prirody.sk", "bohatstvo-prirody.sk", "DogBP3", "Zľava 3 €", "", None),
    ("Bohatstvo-Prirody.sk", "bohatstvo-prirody.sk", "dognet", "Zľava 1 %", "", None),

    # ── druhá dávka ──────────────────────────────────────────────────
    # Popisy, ktoré prišli po česky ("Sleva 5 % na vše"), sú preložené -
    # na slovenskej stránke by česká veta vedľa slovenských pôsobila
    # ako nedorobok.
    ("4Home.sk", "4home.sk", "JESEN4", "Zľava 4 €",
     "Jesenná kolekcia. Platí pri nákupe nad 40 €.", "2026-09-28"),
    ("Lumories.sk", "lumories.sk", "JESEN", "Zľava 13 %",
     "Jeseň vo veľkom štýle - extra zľava na takmer všetko.", "2026-09-27"),
    ("Puravia.sk", "puravia.sk", "Dnipuravia15", "Zľava 15 %", "", "2026-09-23"),
    ("180celsius.com", "180celsius.com", "AFFDNDR", "Zľava 5 %", "", None),
    ("Medosviecky.sk", "medosviecky.sk", "medognet", "Zľava 10 %",
     "Na nezľavnený tovar. Kupón sa dá využiť raz na zákazníka.", None),
    ("Tozax.sk", "tozax.sk", "Afil3", "Zľava 13 %", "Na všetky produkty.", None),
    ("Vypredaj-regalov.sk", "vypredaj-regalov.sk", "77rtn2gfj7", "Zľava 5 %", "Na všetko.", "2030-05-20"),
    ("HomePoint.sk", "homepoint.sk", "Dognet5", "Zľava 5 %", "Na celý nákup.", None),
    ("Alkoshop.sk", "alkoshop.sk", "alkoshop5", "Zľava 5 %",
     "Na všetko. Platí len na nezľavnený tovar.", None),
    ("4Home.sk", "4home.sk", "AFS3", "Zľava 3 %", "Na celý nákup.", "2026-12-31"),
    ("4Home.sk", "4home.sk", "AF3", "Zľava 3 €", "", "2026-12-31"),
    ("Desirel.sk", "desirel.sk", "25DNET", "Zľava 5 %",
     "Minimálna hodnota nákupu 25 €. Nevzťahuje sa na zľavnené položky.", "2026-12-31"),
    ("Kbloom.sk", "kbloom.sk", "dognet5", "Zľava 5 %", "Na čokoľvek.", None),
    ("Real-soft.sk", "real-soft.sk", "X10RP", "Zľava 10 %", "", "2042-12-31"),
    ("Valachshop.sk", "valachshop.sk", "DOGNET5", "Zľava 5 %",
     "Pri nákupe nad 50 €. Platí na nezľavnený tovar.", "2026-12-31"),
    ("Erexan.sk", "erexan.sk", "inspi5", "Zľava 5 %",
     "Platí pri nákupe nad 35 €. Jeden zákazník ho môže využiť raz.", None),
]

# Hemnia.com/sk (10CBDEUR) a budsforbuddies.com/sk (10BFBEUR) sem
# zámerne nepatria: v Dognete majú platnosť OD 21. 11. 2026, teda
# v budúcnosti. Zverejniť kód, ktorý dnes nefunguje, je horšie než
# nezverejniť nič - človek ho skúsi, nezaberie a stratí dôveru.
# Pridáme ich, keď im platnosť začne.

# CisteOblecenie.sk má v Dognete "Kupón s automatickou aktiváciou" -
# nie je to kód, ktorý by si človek niekam prepísal, zľava sa aktivuje
# preklikom. Do zoznamu kódov nepatrí, nebolo by čo skopírovať.


def _kluc(store: str, code: str) -> tuple[str, str]:
    """Rovnaký kód môže mať viac e-shopov, preto porovnávame oboje."""
    return (store.strip().lower().rstrip("."), code.strip().lower())


def _sk_datum(iso: str) -> str:
    r, m, d = iso.split("-")
    return f"{int(d)}. {int(m)}. {r}"


def main() -> int:
    dry = "--skuska" in sys.argv

    import firestore_client
    from google.cloud import firestore as fs
    db = firestore_client.get_client()

    existujuce = set()
    for doc in db.collection("coupons").stream():
        c = doc.to_dict() or {}
        if c.get("code"):
            existujuce.add(_kluc(c.get("store", ""), c["code"]))

    logger.info("Na stránke je %d kódov, v zozname z Dognetu %d.\n", len(existujuce), len(KUPONY))

    pridane = preskocene = 0
    for store, domain, code, discount, popis, do_iso in KUPONY:
        if _kluc(store, code) in existujuce:
            logger.info(" = %-22s %-16s (už tam je)", store, code)
            preskocene += 1
            continue

        zaznam = {
            "author": "Deal Hunter",
            "code": code,
            "store": store,
            "discount": discount,
            "description": popis,
            "url": f"https://www.{domain}",
            "expiryDate": _sk_datum(do_iso) if do_iso else None,
            "status": "approved",
            "votes": 0,
            "timestamp": fs.SERVER_TIMESTAMP,
        }
        if do_iso:
            zaznam["expiryISO"] = do_iso

        if dry:
            logger.info(" ? %-22s %-16s %s", store, code, discount)
        else:
            db.collection("coupons").add(zaznam)
            logger.info(" + %-22s %-16s %s", store, code, discount)
        pridane += 1

    logger.info("\n%s %d, preskočených %d.",
                "Pridalo by sa" if dry else "Pridaných", pridane, preskocene)
    return 0


if __name__ == "__main__":
    sys.exit(main())
