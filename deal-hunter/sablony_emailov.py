"""
Šablóny e-mailov, ktoré posiela Firebase (overenie e-mailu, zabudnuté
heslo, zmena adresy).

PREČO SÚBORY A NIE KÓD V ADMINE
Tieto tri e-maily neposiela naša stránka ani plánovač, ale samotný
Firebase - text aj vzhľad si drží vo svojej konzole. Nedá sa tam zapisovať
z kódu, treba ich raz vložiť ručne. Aby vyzerali rovnako ako ostatné naše
e-maily, vygenerujeme ich tým istým šablónovačom (emaily._html) do
assets/emaily/ a admin ich odtiaľ ponúkne na skopírovanie.

Spustenie po každej zmene vzhľadu e-mailov:
    python sablony_emailov.py
"""

from __future__ import annotations

import json
from pathlib import Path

import emaily

# %LINK% a %NEW_EMAIL% doplní Firebase pri odoslaní.
SABLONY = {
    "overenie": {
        "nazov": "Overenie e-mailu po registrácii",
        "kde": "Firebase → Authentication → Templates → Email address verification",
        "predmet": "Potvrď svoj e-mail na HenKukaj.sk",
        "text": ("Ahoj,\n\nvitaj na HenKukaj.sk! Ešte jeden klik a máš hotovo – potvrď, že tento e-mail patrí tebe.\n\n"
                 "Potom si môžeš ukladať dealy, nastaviť si strážcu zliav a dostávať len to, čo ťa naozaj zaujíma.\n\n"
                 "Ak si sa neregistroval ty, tento e-mail pokojne zahoď. Bez potvrdenia sa nič nestane.\n\n"
                 "Tím HenKukaj.sk"),
        "tlacidlo": ("Potvrdiť e-mail", "%LINK%"),
    },
    "heslo": {
        "nazov": "Zabudnuté heslo",
        "kde": "Firebase → Authentication → Templates → Password reset",
        "predmet": "Nové heslo na HenKukaj.sk",
        "text": ("Ahoj,\n\nposlali sme ti odkaz na nastavenie nového hesla. Platí hodinu a použiť sa dá raz.\n\n"
                 "Ak si o zmenu nežiadal, nemusíš robiť nič – tvoje pôvodné heslo ostáva v platnosti.\n\n"
                 "Tím HenKukaj.sk"),
        "tlacidlo": ("Nastaviť nové heslo", "%LINK%"),
    },
    "zmena": {
        "nazov": "Zmena e-mailu v účte",
        "kde": "Firebase → Authentication → Templates → Email address change",
        "predmet": "V tvojom účte sa zmenila e-mailová adresa",
        "text": ("Ahoj,\n\ne-mail v tvojom účte na HenKukaj.sk bol zmenený na %NEW_EMAIL%.\n\n"
                 "Ak si to nebol ty, klikni nižšie – adresu vrátime späť na túto. Potom si hneď zmeň heslo.\n\n"
                 "Tím HenKukaj.sk"),
        "tlacidlo": ("Vrátiť pôvodnú adresu", "%LINK%"),
    },
}


def main() -> int:
    kam = Path(__file__).resolve().parent.parent / "assets" / "emaily"
    kam.mkdir(parents=True, exist_ok=True)
    zoznam = []
    for kluc, s in SABLONY.items():
        html = emaily._html(s["text"], tlacidlo=s["tlacidlo"])
        (kam / f"{kluc}.html").write_text(html, encoding="utf-8")
        zoznam.append({"kluc": kluc, "nazov": s["nazov"], "kde": s["kde"], "predmet": s["predmet"]})
    (kam / "zoznam.json").write_text(json.dumps(zoznam, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Vygenerovaných {len(zoznam)} šablón do {kam}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
