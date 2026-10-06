"""
Šablóna e-mailu "Zmena e-mailu v účte" - jediná, ktorú ešte posiela
priamo Firebase vlastným textom (zriedkavý jav, menej priorita).

Overenie e-mailu a zabudnuté heslo tu predtým tiež boli, ale tie dnes
posiela náš plánovač (ucty.py) a predmet aj text sa upravujú v admin
zóne (E-maily) s rovno živým náhľadom - samostatný statický súbor by
sa od skutočného znenia len rozchádzal.

Spustenie po zmene vzhľadu e-mailov:
    python sablony_emailov.py
"""

from __future__ import annotations

import json
from pathlib import Path

import emaily

# %LINK% a %NEW_EMAIL% doplní Firebase pri odoslaní.
SABLONY = {
    "zmena": {
        "nazov": "Zmena e-mailu v účte",
        "kde": "Posiela Firebase vlastným textom (ak si niekto zmení adresu). Stáva sa to zriedka.",
        "firebase": False,
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
        zoznam.append({"kluc": kluc, "nazov": s["nazov"], "kde": s["kde"],
                       "predmet": s["predmet"], "firebase": s.get("firebase", False)})
    (kam / "zoznam.json").write_text(json.dumps(zoznam, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Vygenerovaných {len(zoznam)} šablón do {kam}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
