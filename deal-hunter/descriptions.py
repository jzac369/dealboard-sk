"""
Generovanie popiskov k dealom.

Popisok má znieť ako od človeka — v prvej osobe, 3 až 4 vety.

ČO TU ZÁMERNE NIE JE
Popisok nikdy netvrdí nič, čo sa nedá overiť z dát: že som produkt kúpil,
vyskúšal, že je to historicky najnižšia cena alebo že je kusov málo.
Také vety by boli vymyslené a stránke by uškodili viac, než by pomohli —
čitateľ ich raz overí a stratí dôveru v celý web. Nadšenie a vlastný
názor sú v poriadku, vymyslené fakty nie.

Vety sa skladajú zo štyroch častí:
  1. úvod       — ako som na to narazil
  2. fakt       — cena a zľava (jediné tvrdé čísla, všetky z dát)
  3. názor      — subjektívny komentár, ladený podľa kategórie
  4. záver      — platnosť alebo výzva

Výber je deterministický (seed = dedupe kľúč), takže ten istý deal má
vždy ten istý popisok a dva rôzne dealy majú takmer vždy iný.
"""

import random
from typing import Optional

# ── 1. úvody ──────────────────────────────────────────────────────────
# {store} = obchod
_OPENERS_LEAFLET = [
    "Prezeral som si leták {store} a toto mi padlo do oka.",
    "Našiel som toto v aktuálnom letáku {store}.",
    "Pri listovaní letáku {store} som narazil na túto ponuku.",
    "Toto sa objavilo v akcii v {store} a stálo mi za zastavenie.",
    "V {store} teraz bežia zľavy a toto je z nich podľa mňa najzaujímavejšie.",
    "Kontroloval som, čo je tento týždeň v akcii v {store}, a toto ma zaujalo.",
]

# ── 2. fakty o cene ───────────────────────────────────────────────────
# {old} {new} {pct} — všetko priamo z dát
_PRICE_FACTS = [
    "Cena spadla z {old} € na {new} €, teda o {pct} % dole.",
    "Z pôvodných {old} € je teraz {new} €, čo je zľava {pct} %.",
    "Namiesto {old} € zaplatíš {new} € — {pct} % preč.",
    "Pôvodne {old} €, teraz {new} €. To je {pct} % zľava.",
    "Zlacnené z {old} € na {new} €, čiže o {pct} %.",
]

# ── 3. názory podľa výšky zľavy ───────────────────────────────────────
_OPINION_HUGE = [  # 50 % a viac
    "Takto veľká zľava sa neobjavuje často, takže si to rozhodne pozri.",
    "Pri takomto prepade ceny neváham a hovorím o tom ďalej.",
    "To už je poriadny rozdiel, nie kozmetická zľava.",
    "Zľavy v tejto výške sa mi do zoznamu dostanú len párkrát do mesiaca.",
]
_OPINION_GOOD = [  # 35-50 %
    "To je podľa mňa slušná ponuka, ktorá stojí za zváženie.",
    "Za túto cenu mi to dáva zmysel.",
    "Nie je to zľava storočia, ale rozdiel je citeľný.",
    "Takúto cenu považujem za dobrý dôvod siahnuť po tom teraz.",
]
_OPINION_OK = [  # 25-35 %
    "Nie je to trhák, ale ak to práve potrebuješ, teraz je na to vhodná chvíľa.",
    "Rozdiel v cene je dosť veľký na to, aby sa oplatilo počkať si na akciu.",
    "Ak to máš aj tak v pláne kúpiť, teraz to vyjde lacnejšie.",
]

# ── 3b. doplnkové vety podľa kategórie ────────────────────────────────
_CATEGORY_NOTES = {
    "Jedlo & Nápoje": [
        "Pri potravinách sledujem hlavne dátum spotreby, tak sa naň pozri priamo v predajni.",
        "Také veci si beriem do zásoby, keď sú v akcii.",
        "Pri jedle sa akcie striedajú rýchlo, takže to nemusí vydržať dlho.",
    ],
    "Dom & Záhrada": [
        "Pri vybavení do domácnosti sa oplatí porovnať rozmery, než to objednáš.",
        "Také veci človek kupuje raz za dlhý čas, tak nech to stojí za to.",
    ],
    "Elektronika": [
        "Pri elektronike si vždy pozri aj dĺžku záruky.",
        "Odporúčam pozrieť si parametre, či to sedí na to, na čo to potrebuješ.",
    ],
    "Šport": [
        "Na šport sa mi oplatí nakupovať mimo sezóny, presne ako teraz.",
    ],
    "Hračky": [
        "Ak hľadáš darček dopredu, takto sa dá ušetriť.",
    ],
}

# ── 4. závery ─────────────────────────────────────────────────────────
_CLOSERS_WITH_DATE = [
    "Akcia platí do {until}, potom sa cena vracia späť.",
    "Platí to do {until}, tak s tým nečakaj príliš dlho.",
    "Termín je do {until} — dovtedy to stihneš.",
    "Do {until} je to za túto cenu, potom už nie.",
]
_CLOSERS_PLAIN = [
    "Ak ťa to zaujme, klikni na odkaz a pozri si detaily.",
    "Detaily nájdeš cez odkaz nižšie.",
    "Viac sa dozvieš priamo u predajcu.",
    "Mrkni na to, nech ti to neutečie.",
]


def _pick(rng: random.Random, pool: list[str]) -> str:
    return pool[rng.randrange(len(pool))]


def _format_price(value: float) -> str:
    """4.99 -> '4,99' (slovenský desatinný oddeľovač)."""
    return f"{value:.2f}".replace(".", ",")


def build_description(
    *,
    store: str,
    category: str,
    old_price: float,
    new_price: float,
    discount_percent: float,
    valid_until: Optional[str] = None,
    seed: str = "",
) -> str:
    """
    Zloží 3-4 vetový popisok v prvej osobe.

    Seed zabezpečí, že ten istý deal dostane vždy rovnaký text — inak by
    sa popisok menil pri každom spustení a pôsobilo by to neprirodzene.
    """
    rng = random.Random(seed or store + str(new_price))

    opener = _pick(rng, _OPENERS_LEAFLET).format(store=store or "obchodu")

    fact = _pick(rng, _PRICE_FACTS).format(
        old=_format_price(old_price),
        new=_format_price(new_price),
        pct=round(discount_percent),
    )

    if discount_percent >= 50:
        opinion = _pick(rng, _OPINION_HUGE)
    elif discount_percent >= 35:
        opinion = _pick(rng, _OPINION_GOOD)
    else:
        opinion = _pick(rng, _OPINION_OK)

    sentences = [opener, fact, opinion]

    # Štvrtú vetu pridáme len občas, aby popisky neboli všetky rovnako dlhé.
    category_notes = _CATEGORY_NOTES.get(category)
    if category_notes and rng.random() < 0.45:
        sentences.append(_pick(rng, category_notes))

    if valid_until:
        sentences.append(_pick(rng, _CLOSERS_WITH_DATE).format(until=valid_until))
    else:
        sentences.append(_pick(rng, _CLOSERS_PLAIN))

    # Držíme sa 3-4 viet: ak ich je päť, vyhodíme názor na kategóriu.
    if len(sentences) > 4:
        sentences.pop(3)

    return " ".join(sentences)
