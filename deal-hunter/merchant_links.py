"""
Odkazy priamo k predajcovi namiesto na sprostredkovateľa.

PREČO TO NIE JE PRIAMY ODKAZ NA PRODUKT
Ponuky pochádzajú z letákov reťazcov a väčšina takých položiek vlastnú
produktovú stránku vôbec nemá — "Hrozno červené 500 g" v BILLE nie je
e-shopová položka, existuje len v letáku. Zdroj (zlacnene.sk) navyše na
predajcu neodkazuje vôbec.

Preto dve úrovne, od najlepšej po najhoršiu:

1. Predajca má e-shop s vyhľadávaním -> odkaz na výsledky hľadania podľa
   názvu produktu. Používateľ skončí priamo pri tovare.
2. Predajca e-shop nemá (potravinové reťazce) -> odkaz na jeho stránku
   s akciami alebo na hlavnú stránku.

Tvary URL vo VYHLADAVANIE sú overené — každý vrátil HTTP 200 a bol
odčítaný priamo z vyhľadávacieho formulára daného webu, nie odhadnutý.
"""

import logging
import re
import unicodedata
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Predajcovia s e-shopom: {q} sa nahradí názvom produktu.
VYHLADAVANIE: dict[str, str] = {
    "jysk": "https://jysk.sk/search?query={q}",
    "obi": "https://www.obi.sk/search/{q}/",
    "stavmat": "https://www.stavmat.sk/vyhladavanie/?search={q}",
    "sconto": "https://www.sconto.sk/hledani?q={q}",
}

# Predajcovia bez použiteľného vyhľadávania — odkaz na ich stránku.
# Pri potravinových reťazcoch mieri rovno na akcie/letáky.
STRANKA_PREDAJCU: dict[str, str] = {
    "billa": "https://www.billa.sk/akcie",
    "tesco": "https://www.tesco.sk/",
    "kaufland": "https://www.kaufland.sk/",
    "lidl": "https://www.lidl.sk/",
    "xxxlutz": "https://www.xxxlutz.sk/",
    "ideanabytok": "https://www.idea-nabytok.sk/",
    "idea": "https://www.idea-nabytok.sk/",
    "jysk": "https://jysk.sk/",
    "kik": "https://www.kik.sk/",
    "moebelix": "https://www.moebelix.sk/",
    "asko": "https://www.asko-nabytok.sk/",
    "nay": "https://www.nay.sk/",
    "datart": "https://www.datart.sk/",
    "alza": "https://www.alza.sk/",
    "intersport": "https://www.intersport.sk/",
    "bauhaus": "https://www.bauhaus.sk/",
    "mobelix": "https://www.moebelix.sk/",
    "dm": "https://www.mojadm.sk/",
    "teta": "https://www.tetadrogerie.sk/",
    "hornbach": "https://www.hornbach.sk/",
    "decathlon": "https://www.decathlon.sk/",
    "pepco": "https://pepco.sk/",
    "action": "https://www.action.com/sk-sk/",
}


def _normalise(store: str) -> str:
    """'XXXLutz' / 'SCONTO nábytok' -> 'xxxlutz' / 'sconto'."""
    text = unicodedata.normalize("NFKD", store.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text)


def _match(store: str, table: dict[str, str]) -> str | None:
    """
    Nájde predajcu v tabuľke. Porovnáva aj čiastočne, lebo zdroj píše mená
    rôzne — "SCONTO nábytok", "BILLA", "Jysk" aj "JYSK A/S".
    """
    key = _normalise(store)
    if not key:
        return None
    if key in table:
        return table[key]
    for known, url in table.items():
        if known in key:
            return url
    return None


def build_merchant_url(store: str, title: str, fallback: str) -> str:
    """
    Vráti najlepší dostupný odkaz k predajcovi.

    `fallback` (odkaz na zdroj) sa použije len vtedy, keď predajcu vôbec
    nepoznáme. Hádať doménu podľa mena nechceme — trafili by sme cudziu
    firmu a poslali návštevníka inam, než si myslí.
    """
    search_template = _match(store, _overrides_search) or _match(store, VYHLADAVANIE)
    if search_template:
        # safe="" zakóduje aj lomky. Bez toho by názov typu
        # "TC-AC 190/24/8" rozbil cestu v URL (napr. u OBI).
        return search_template.format(q=quote(_clean_title(title), safe=""))

    merchant_page = _match(store, _overrides_page) or _match(store, STRANKA_PREDAJCU)
    if merchant_page:
        return merchant_page

    logger.info(
        "Predajcu '%s' nepoznám — nechávam odkaz na zdroj. "
        "Doplň ho do merchant_links.py.", store,
    )
    return fallback


def _clean_title(title: str) -> str:
    """
    Vyčistí názov pre vyhľadávanie. Zdroj pridáva pred názov poradové
    číslo z letáku ("16: Vintage koberec") a za názov gramáž — ani jedno
    vo vyhľadávaní e-shopu nepomáha.
    """
    cleaned = re.sub(r"^\s*\d+\s*:\s*", "", title)
    # Zdroj obaľuje značky francúzskymi a typografickými úvodzovkami.
    cleaned = re.sub("[«»“”„‚‘’]", "", cleaned)
    # Gramáže a objemy na konci ("500 g", "1,5 l", "8 ks/1 bal.")
    cleaned = re.sub(
        r"[,\s]*\b\d+[.,]?\d*\s*(g|kg|ml|l|ks|bal|cm|mm|m)\b.*$",
        "", cleaned, flags=re.IGNORECASE,
    )
    # Lomky preč: pri vyhľadávaní cez cestu v URL (OBI) ich ani zakódované
    # server neprijme a vráti 404.
    cleaned = cleaned.replace("/", " ")
    return " ".join(cleaned.split())[:60].strip(" ,-")


# ── predajcovia spravovaní z admin panelu ─────────────────────────────
# Tabuľky vyššie sú východiskové a sú v kóde. Cez admin panel sa dajú
# dopĺňať a prepisovať bez toho, aby som musel meniť kód a nasadzovať.

_overrides_search: dict[str, str] = {}
_overrides_page: dict[str, str] = {}


def load_overrides(db) -> int:
    """
    Načíta predajcov z kolekcie `merchants`. Záznam z admin panelu má
    prednosť pred tabuľkou v kóde — inak by sa tvoja úprava po každom
    nasadení stratila.

    Keď kolekcia neexistuje alebo sa nedá prečítať, ticho pokračujeme
    s tabuľkami v kóde. Chýbajúci prepis nie je dôvod zhodiť beh.
    """
    _overrides_search.clear()
    _overrides_page.clear()

    try:
        for doc in db.collection("merchants").stream():
            data = doc.to_dict() or {}
            key = _normalise(data.get("name") or doc.id)
            if not key:
                continue
            if data.get("searchUrl"):
                _overrides_search[key] = data["searchUrl"]
            elif data.get("pageUrl"):
                _overrides_page[key] = data["pageUrl"]
    except Exception as e:
        logger.warning("Predajcovia z admin panelu sa nenačítali: %s", e)
        return 0

    count = len(_overrides_search) + len(_overrides_page)
    if count:
        logger.info("Načítaných %d predajcov z admin panelu", count)
    return count


# ── affiliate tracking ────────────────────────────────────────────────

# Parametre, podľa ktorých spoznáme, že odkaz už tracking nesie.
_TRACKING_PARAMS = {"a_aid", "a_bid", "a_cid", "aff", "affid", "pid", "clickref", "utm_source"}


def add_affiliate_tracking(url: str) -> str:
    """
    Obalí odkaz partnerskou šablónou, ak ju máme nastavenú a odkaz ešte
    tracking neobsahuje.

    Prečo to vôbec riešime: časť sietí dáva vo feede obyčajné adresy
    e-shopu. Bez obalenia by dealy fungovali, ale nezarobili by nič — a
    to je jediný dôvod, prečo sa affiliate feedy vôbec zapájajú.

    Šablóna sa nastavuje cez premennú AFFILIATE_LINK_TEMPLATE a musí
    obsahovať {url}. Do repozitára nepatrí, je v nej partnerské ID.
    """
    import config
    from urllib.parse import parse_qs, quote, urlparse

    if not url or not url.startswith("http"):
        return url

    template = getattr(config, "AFFILIATE_LINK_TEMPLATE", "")
    if not template or "{url}" not in template:
        return url

    if _TRACKING_PARAMS & set(parse_qs(urlparse(url).query)):
        return url   # už otagované sieťou, druhýkrát by to tracking rozbilo

    return template.replace("{url}", quote(url, safe=""))


def is_known(store: str) -> bool:
    """
    True, keď pre daný obchod vieme zostaviť odkaz k predajcovi.

    Používa sa na to, aby sa na stránku nedostal deal odkazujúci na
    zdroj namiesto obchodu. Radšej deal vynechať, než poslať
    návštevníka na konkurenčný web.
    """
    return bool(
        _match(store, _overrides_search) or _match(store, _overrides_page)
        or _match(store, VYHLADAVANIE) or _match(store, STRANKA_PREDAJCU)
    )
