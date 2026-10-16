"""
Publikovanie tipov z adminu na stránku.

Admin (Tipy medzi dealmi) uloží nahrané obrázky do Firestore (kolekcia
tipy_cakaren) a zapíše tipy do settings/tipy. Tento skript ich zmení na
súbory assets/tipy/<id>.jpg v repozitári - stránka ich tak servíruje z
GitHub Pages (rýchlo, z cache) a nie z databázy, kde by každé zobrazenie
stálo prenos desiatok kilobajtov.

Potom workflow súbory commitne. Skript:
  - uloží obrázok ako JPEG (max. šírka 1200 px),
  - doplní do tipu cestu k súboru,
  - zmaže spracované dokumenty z tipy_cakaren,
  - zmaže súbory tipov, ktoré v adminovi už neexistujú.
"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
from pathlib import Path

from PIL import Image

import firestore_client

logger = logging.getLogger(__name__)

KOREN = Path(__file__).resolve().parents[1]
PRIECINOK = KOREN / "assets" / "tipy"
MAX_SIRKA = 1200
ID_RE = re.compile(r"^[a-z0-9]{4,24}$")


def _obrazok_z_dat(data_url: str) -> Image.Image:
    m = re.match(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", data_url or "", re.S)
    if not m:
        raise ValueError("Neplatný obrázok.")
    im = Image.open(io.BytesIO(base64.b64decode(m.group(2))))
    im.load()
    return im.convert("RGB")


def _uloz(im: Image.Image, cesta: Path) -> None:
    if im.width > MAX_SIRKA:
        im = im.resize((MAX_SIRKA, round(im.height * MAX_SIRKA / im.width)), Image.LANCZOS)
    cesta.parent.mkdir(parents=True, exist_ok=True)
    im.save(cesta, "JPEG", quality=86, optimize=True, progressive=True)


def publikuj(db) -> dict:
    ref = db.document("settings/tipy")
    nastavenia = ref.get().to_dict() or {}
    tipy = list(nastavenia.get("tipy") or [])
    podla_id = {t.get("id"): t for t in tipy}

    spracovane = 0
    chyby = []
    verzia = int(time.time())
    for doc in db.collection("tipy_cakaren").stream():
        d = doc.to_dict() or {}
        tid = doc.id
        if not ID_RE.match(tid) or tid not in podla_id:
            # Tip medzitým zmazali alebo ID nie je bezpečné - nič nepíšeme.
            doc.reference.delete()
            continue
        try:
            _uloz(_obrazok_z_dat(d.get("dataUrl")), PRIECINOK / f"{tid}.jpg")
            if d.get("mobilDataUrl"):
                _uloz(_obrazok_z_dat(d["mobilDataUrl"]), PRIECINOK / f"{tid}-m.jpg")
                podla_id[tid]["mobil"] = f"assets/tipy/{tid}-m.jpg?v={verzia}"
            podla_id[tid]["obrazok"] = f"assets/tipy/{tid}.jpg?v={verzia}"
            doc.reference.delete()
            spracovane += 1
        except Exception as e:  # jeden chybný obrázok nesmie zablokovať ostatné
            logger.error("Tip %s: %s", tid, e)
            chyby.append(f"{tid}: {e}")
            podla_id[tid]["chyba"] = str(e)[:120]

    if spracovane or chyby:
        ref.set({"tipy": tipy}, merge=True)

    # Súbory tipov, ktoré už v adminovi nie sú.
    platne = set()
    for t in tipy:
        if t.get("id") and ID_RE.match(t["id"]):
            platne.add(f"{t['id']}.jpg")
            platne.add(f"{t['id']}-m.jpg")
    zmazane = 0
    for f in PRIECINOK.glob("*.jpg"):
        if f.name not in platne:
            f.unlink()
            zmazane += 1
    for f in PRIECINOK.glob("tipy.json"):
        f.unlink()   # starý zoznam zo súboru - zdrojom je teraz admin
    return {"publikovane": spracovane, "zmazane": zmazane, "chyby": chyby}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    vysledok = publikuj(firestore_client.get_client())
    logger.info("Tipy: %s", vysledok)
    return 1 if vysledok["chyby"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
