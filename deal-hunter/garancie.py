"""
Garantovaný denný deal z vybraných obchodov (Allegro, lekárne).

select_best radí čisto podľa zľavy, takže obchod s menšími percentami
(Allegro, lekárne) by sa do výberu nikdy nedostal. Tu si za každú
skupinu rezervujeme jedno miesto denne: ak v dnešných zápisoch ešte
nebola a v aktuálnom behu je z nej kandidát, pôjde dopredu.
"""

import config

# názov skupiny -> kúsky názvu obchodu (bez diakritiky, malými písmenami)
SKUPINY: dict[str, tuple[str, ...]] = {
    "allegro": ("allegro",),
    "lekaren": ("lekaren", "benu", "lieky"),
    "freebie": (),   # určuje sa podľa príznaku zadarmo, nie podľa názvu obchodu
}


def _bez_diakritiky(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")


def skupina_dealu(c) -> str | None:
    """Skupina kandidáta: freebie má vlastnú, inak podľa obchodu."""
    if getattr(c, "zadarmo", False):
        return "freebie"
    return skupina_obchodu(c.store or c.source)


def skupina_obchodu(store: str) -> str | None:
    nazov = _bez_diakritiky(store or "")
    for skupina, kusky in SKUPINY.items():
        if any(k in nazov for k in kusky):
            return skupina
    return None


def pridaj_garantovane(vybrane: list, kandidati: list, splnene: set[str]) -> list:
    """Vráti výber s garantovanými kandidátmi na začiatku (prežijú denný strop)."""
    maju = {skupina_dealu(c) for c in vybrane}
    navyse = []
    for skupina in SKUPINY:
        if skupina in splnene or skupina in maju:
            continue
        z_skupiny = [c for c in kandidati
                     if skupina_dealu(c) == skupina and c not in vybrane]
        if z_skupiny:
            navyse.append(max(z_skupiny, key=lambda c: c.discount_percent))
    return navyse + vybrane
