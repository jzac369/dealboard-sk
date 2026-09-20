"""
História cien a odhaľovanie falošných zliav.

PREČO TO POTREBUJEME
Zľava sa počíta z „pôvodnej ceny", ktorú udáva predajca. Tú si však
určuje sám a je bežnou praktikou ju pred akciou nafúknuť: tovar za
20 € sa preceníkuje na 40 € a potom sa predáva „so zľavou 50 %" za tých
istých 20 €. Deal stránka, ktorá takú ponuku zverejní ako trhák,
klame svojich čitateľov — aj keď nechtiac.

Jediná obrana je pamäť. Ak sme ten istý produkt videli minulý mesiac
za 20 €, vieme, že dnešná „pôvodná cena 40 €" je vymyslená.

AKO TO UKLADÁME
História sa drží priamo v dokumente dealu ako pole `priceHistory`
(zoznam {date, price}). Zámerne nie vo vlastnej kolekcii: tá by
vyžadovala nové Firestore pravidlá, a agentova pamäť aj tak pozná
každý produkt cez dedupe kľúč.
"""

import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# Koľko cenových záznamov si pri produkte pamätáme.
MAX_HISTORY_POINTS = 24

# O koľko % musí byť udávaná pôvodná cena vyššia než historické maximum
# skutočnej ceny, aby sme ju označili za podozrivú. Menšie rozdiely
# môžu byť bežné sezónne výkyvy.
SUSPICIOUS_MARKUP_PERCENT = 20.0


def append_price_point(history: Optional[list], price: float) -> list:
    """
    Pridá dnešnú cenu do histórie. Ak už dnešný záznam existuje,
    prepíše ho — inak by tri behy denne vyrobili tri rovnaké body.
    """
    points = list(history or [])
    today = date.today().isoformat()

    for point in points:
        if point.get("date") == today:
            point["price"] = round(price, 2)
            break
    else:
        points.append({"date": today, "price": round(price, 2)})

    return points[-MAX_HISTORY_POINTS:]


def lowest_seen(history: Optional[list]) -> Optional[float]:
    """Najnižšia cena, akú sme pri tomto produkte kedy videli."""
    prices = [p.get("price") for p in (history or []) if isinstance(p.get("price"), (int, float))]
    return min(prices) if prices else None


def highest_seen(history: Optional[list]) -> Optional[float]:
    prices = [p.get("price") for p in (history or []) if isinstance(p.get("price"), (int, float))]
    return max(prices) if prices else None


def is_real_low(history: Optional[list], price: float) -> bool:
    """True, ak je dnešná cena naozaj najnižšia, akú sme videli."""
    previous = [
        p.get("price") for p in (history or [])
        if isinstance(p.get("price"), (int, float)) and p.get("date") != date.today().isoformat()
    ]
    return bool(previous) and price < min(previous)


def looks_like_fake_discount(
    history: Optional[list], claimed_original: float, current_price: float
) -> tuple[bool, str]:
    """
    Posúdi, či „pôvodná cena" nie je nafúknutá.

    Vráti (je_podozrivá, dôvod). Bez histórie sa nedá povedať nič —
    vtedy vraciame False, lebo obviňovať bez dôkazu je horšie než mlčať.
    """
    if not history or claimed_original <= 0:
        return False, ""

    peak = highest_seen(history)
    if peak is None:
        return False, ""

    # Ak sme produkt nikdy nevideli drahší než X, ale predajca tvrdí,
    # že bežne stojí výrazne viac, je to podozrivé.
    threshold = peak * (1 + SUSPICIOUS_MARKUP_PERCENT / 100)
    if claimed_original > threshold:
        return True, (
            f"udávaná pôvodná cena {claimed_original:.2f} € je o "
            f"{(claimed_original / peak - 1) * 100:.0f} % vyššia než najvyššia "
            f"cena, akú sme pri tomto produkte videli ({peak:.2f} €)"
        )

    # Druhý prípad: "zľava", po ktorej je cena rovnaká alebo vyššia než
    # to, za čo sa produkt bežne predával.
    lowest = lowest_seen(history)
    if lowest is not None and current_price > lowest:
        return True, (
            f"akciová cena {current_price:.2f} € je vyššia než bežná cena "
            f"{lowest:.2f} €, ktorú sme už videli"
        )

    return False, ""
