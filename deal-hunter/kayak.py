"""
Kayak Affiliate Network - sandbox.

ČO S TÝM CHCEME ROBIŤ
Letenková mapa dnes stojí na Ryanairi, takže ukazuje ceny jediného
dopravcu. Kayak má "Flights Price Insights" - najlacnejšie ceny, aké
naposledy videli ich cestujúci - a to je presne to isté, len naprieč
všetkými dopravcami.

PREČO PRÁVE TOTO API A NIE VYHĽADÁVANIE
Stránka je statická, bez servera. Vyhľadávanie by si pýtalo volanie pri
každom hľadaní návštevníka, čo by znamenalo kľúč v prehliadači - a ten
by si vzal ktokoľvek. Price Insights sa stiahne raz denne tu, v GitHub
Actions, a stránka číta hotový súbor. Kľúč zostane v tajomstvách.

SANDBOX NIE JE OSTRÁ PREVÁDZKA
Vracia vymyslené ceny. Slúži na overenie, že integrácia funguje; na
stránku sa z neho nesmie dostať nič.

Adresa aj tvar volania sú z verejného kódu developers.kayak.com -
dokumentácia je za prihlásením.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

ZAKLAD = os.environ.get("KAYAK_API_BASE", "https://sandbox-en-us.kayakaffiliates.com")
KLUC = os.environ.get("KAYAK_API_KEY", "")

# Jediná cesta, ktorú poznáme isto - je vo verejnom kóde ich stránky.
AUTOCOMPLETE = "/api/affiliate/autocomplete/v1/flights"

# Kľúč sa posiela ako parameter "apiKey" - overené na sandboxe 5. 10.
# 2026. Pozor na veľké K: "apikey" malým vráti INVALID_API_KEY, čo zvádza
# myslieť si, že je zlý kľúč.
SPOSOBY = [
    ("parameter apiKey", {}, {"apiKey": "{k}"}),
    ("hlavicka X-Api-Key", {"X-Api-Key": "{k}"}, {}),
    ("hlavicka Authorization Bearer", {"Authorization": "Bearer {k}"}, {}),
]

_FUNKCNY: tuple[dict, dict] | None = None


class KayakChyba(Exception):
    pass


def _volaj(cesta: str, parametre: dict, hlavicky: dict, timeout: int = 20):
    url = ZAKLAD + cesta
    if parametre:
        url += "?" + urllib.parse.urlencode(parametre)
    ziadost = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "henkukaj.sk/1.0 (+https://henkukaj.sk)",
        **hlavicky,
    })
    with urllib.request.urlopen(ziadost, timeout=timeout) as odpoved:
        return json.loads(odpoved.read().decode("utf-8"))


def najdi_sposob(logovat: bool = True) -> tuple[dict, dict]:
    """Zistí, ako sa kľúč posiela. Vracia (hlavičky, parametre) so vsadeným kľúčom."""
    global _FUNKCNY
    if _FUNKCNY:
        return _FUNKCNY
    if not KLUC:
        raise KayakChyba("KAYAK_API_KEY nie je nastavený.")

    for nazov, hl_vzor, par_vzor in SPOSOBY:
        hlavicky = {k: v.format(k=KLUC) for k, v in hl_vzor.items()}
        parametre = {k: v.format(k=KLUC) for k, v in par_vzor.items()}
        try:
            _volaj(AUTOCOMPLETE, {**parametre, "searchTerm": "Bratislava"}, hlavicky)
        except urllib.error.HTTPError as e:
            if logovat:
                logger.info("%-30s HTTP %s", nazov, e.code)
            # 401/403 = zlý spôsob. Čokoľvek iné je chyba na našej strane
            # a skúšať ďalšie spôsoby nemá zmysel.
            if e.code not in (400, 401, 403):
                raise KayakChyba(f"{nazov}: HTTP {e.code}") from e
            time.sleep(1)
            continue
        except Exception as e:
            if logovat:
                logger.info("%-30s %s", nazov, e)
            time.sleep(1)
            continue
        if logovat:
            logger.info("%-30s OK", nazov)
        _FUNKCNY = (hlavicky, parametre)
        return _FUNKCNY
    raise KayakChyba("Kľúč neprešiel ani jedným zo skúšaných spôsobov.")


def zavolaj(cesta: str, **parametre):
    hlavicky, zakladne = najdi_sposob(logovat=False)
    return _volaj(cesta, {**zakladne, **parametre}, hlavicky)
