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

import http.cookiejar
import json
import logging
import os
import uuid
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

ZAKLAD = os.environ.get("KAYAK_API_BASE", "https://sandbox-en-us.kayakaffiliates.com")
KLUC = os.environ.get("KAYAK_API_KEY", "")

AUTOCOMPLETE = "/api/affiliate/autocomplete/v1/flights"
# Pozor na predponu "/i/" - autocomplete ju nemá, Price Insights áno.
ROUTES = "/i/api/affiliate/priceInsights/flights/v1/routes"
CALENDAR = "/i/api/affiliate/priceInsights/flights/v1/calendar"

# Kľúč sa posiela ako parameter "apiKey" - overené na sandboxe 5. 10.
# 2026. Pozor na veľké K: "apikey" malým vráti INVALID_API_KEY, čo zvádza
# myslieť si, že je zlý kľúč.
SPOSOBY = [
    ("parameter apiKey", {}, {"apiKey": "{k}"}),
    ("hlavicka X-Api-Key", {"X-Api-Key": "{k}"}, {}),
    ("hlavicka Authorization Bearer", {"Authorization": "Bearer {k}"}, {}),
]

_FUNKCNY: tuple[dict, dict] | None = None

# Server vracia "cluster cookie" - ktoré dátové centrum má ďalšie volania
# obslúžiť. Bez jej vrátenia by nás pri každej žiadosti presmerovával inam.
_SUSIENKY = http.cookiejar.CookieJar()
_OTVARAC = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_SUSIENKY))

# Kayak chce vedieť, za koho sa pýtame. U nás sa ceny sťahujú raz denne
# dávkovo, nie pri návšteve človeka, takže žiadny návštevník neexistuje -
# posielame identifikátor behu. Pred ostrou prevádzkou to treba s nimi
# vyjasniť: ich dokumentácia s týmto použitím zjavne nepočíta.
USER_TRACK_ID = os.environ.get("KAYAK_USER_TRACK_ID") or ("henkukaj-" + uuid.uuid4().hex[:16])


def _moja_ip() -> str:
    """
    Verejná adresa, z ktorej voláme.

    Kayak chce hlavičku x-original-client-ip a upozorňuje, že nesprávne
    údaje skresľujú ich merania. Vymýšľať si adresu návštevníka by bolo
    nepoctivé, tak posielame tú svoju - žiadosť naozaj ide odtiaľto.
    """
    global _IP
    if _IP:
        return _IP
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=10) as o:
            _IP = o.read().decode().strip()
    except Exception:
        _IP = "0.0.0.0"
    return _IP


_IP = ""


class KayakChyba(Exception):
    pass


def _volaj(cesta: str, parametre: dict, hlavicky: dict, telo: dict | None = None,
           timeout: int = 30):
    url = ZAKLAD + cesta
    if parametre:
        url += "?" + urllib.parse.urlencode(parametre)
    data = json.dumps(telo).encode("utf-8") if telo is not None else None
    vsetky = {
        "Accept": "application/json",
        "User-Agent": "henkukaj.sk/1.0 (+https://henkukaj.sk)",
        "x-original-client-ip": _moja_ip(),
        **hlavicky,
    }
    if data is not None:
        vsetky["Content-Type"] = "application/json"
    ziadost = urllib.request.Request(url, data=data, headers=vsetky)
    with _OTVARAC.open(ziadost, timeout=timeout) as odpoved:
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


def _posli(cesta: str, telo: dict):
    hlavicky, zakladne = najdi_sposob(logovat=False)
    return _volaj(cesta, {**zakladne, "userTrackId": USER_TRACK_ID}, hlavicky, telo=telo)


def miesto(nazov: str) -> dict | None:
    """Názov mesta alebo letiska -> záznam s placeId. Prvý letiskový výsledok."""
    data = zavolaj(AUTOCOMPLETE, searchTerm=nazov)
    vysledky = (data or {}).get("results") or []
    for r in vysledky:
        if r.get("primaryPlaceType") == "airport":
            return r
    return vysledky[0] if vysledky else None


def routes(origin_id: int, destination_id: int | None = None, **dalsie):
    """Najlacnejšia cena na každú trasu v danom období."""
    telo: dict = {"origin": {"placeId": origin_id}}
    if destination_id:
        telo["destination"] = {"placeId": destination_id}
    telo.update(dalsie)
    return _posli(ROUTES, telo)


def calendar(origin_id: int, destination_id: int, od: str, do: str, **dalsie):
    """
    Najlacnejšia cena na každý deň v období. `od`/`do` sú "RRRR-MM".

    Toto je to, čo potrebuje naša letenková mapa - na rozdiel od `routes`
    vráti cenu na každý deň, nie jednu najnižšiu za celé obdobie.
    """
    telo = {"origin": {"placeId": origin_id}, "destination": {"placeId": destination_id},
            "dateFrom": od, "dateTo": do}
    telo.update(dalsie)
    return _posli(CALENDAR, telo)
