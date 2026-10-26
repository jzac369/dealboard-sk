"""
Kontrola dostupnosti webu a odkazov dealov. Beží na domácom serveri (NUC).

DVE ÚLOHY A PREČO MAJÚ RÔZNU FREKVENCIU
1) Web (každých 5 minút): jedna malá požiadavka na pár vlastných adries.
   Výpadok webu treba vedieť hneď a takáto kontrola nikoho nezaťažuje.
2) Odkazy dealov (raz denne, --odkazy): ide o desiatky až stovky cudzích
   e-shopov. Častejšie by bolo zaťaženie cudzích serverov a nič by sa tým
   nezískalo, lebo e-shop sa denne nerozpadne.

AKO SA OZNAMUJE
- Výpadok sa oznámi až po dvoch zlyhaniach za sebou (zhruba 10 minút),
  aby jedna chvíľková chyba siete nepísala v noci do Telegramu.
- Oznámi sa to raz (nie každých 5 minút) a keď sa web vráti, príde správa
  "obnovené" aj s dĺžkou výpadku.
- Mŕtve odkazy: dealy, ktorých stránka vrátila 404/410 dva dni po sebe.
  Nič sa automaticky nemení, len príde zoznam do Telegramu na rozhodnutie.

Stav sa pamätá v ~/.henkukaj-monitor.json (len v tomto počítači).
Telegram sa berie z TELEGRAM_BOT_TOKEN a TELEGRAM_CHAT_ID v prostredí.

POUŽITIE
  python monitor.py              kontrola webu
  python monitor.py --odkazy     kontrola odkazov dealov
  python monitor.py --skuska     len vypíše, nič neposiela ani nezapisuje
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("monitor")

STAV_SUBOR = Path.home() / ".henkukaj-monitor.json"
UA = "HenKukajMonitor/1.0 (+https://henkukaj.sk)"

# (názov kontroly, adresa, text, ktorý musí byť na stránke; None = len 200)
KONTROLY = [
    ("web", "https://henkukaj.sk/", "HenKukaj"),
    ("admin", "https://henkukaj.sk/admin.html", None),
    ("sitemap", "https://henkukaj.sk/sitemap.xml", "<urlset"),
    # Databáza: číta sa verejný dokument (rovnako ako web).
    ("databaza", "https://firestore.googleapis.com/v1/projects/dealboard-e60bf/databases/(default)"
                 "/documents/settings/tipy", "fields"),
]

SKUSKA = "--skuska" in sys.argv


def nacitaj_stav() -> dict:
    try:
        return json.loads(STAV_SUBOR.read_text(encoding="utf-8"))
    except Exception:
        return {}


def uloz_stav(stav: dict) -> None:
    if SKUSKA:
        return
    STAV_SUBOR.write_text(json.dumps(stav, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        STAV_SUBOR.chmod(0o600)
    except OSError:
        pass


def posli(text: str) -> None:
    logger.info("Telegram: %s", text.replace("\n", " | "))
    if SKUSKA:
        return
    import telegram_bot
    if not telegram_bot.send_text(text):
        logger.warning("Telegram správa sa neodoslala (nenastavený token alebo chyba).")


def skontroluj(nazov: str, url: str, obsahuje: str | None) -> tuple[bool, str]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    except requests.RequestException as e:
        return False, f"{type(e).__name__}"
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"
    if obsahuje and obsahuje not in r.text:
        return False, "stránka nemá očakávaný obsah"
    return True, "ok"


def kontrola_webu() -> int:
    stav = nacitaj_stav()
    web = stav.setdefault("web", {})
    teraz = datetime.now(timezone.utc)

    for nazov, url, obsahuje in KONTROLY:
        ok, dovod = skontroluj(nazov, url, obsahuje)
        s = web.setdefault(nazov, {"zlyhani": 0, "oznameny": False, "od": None})
        logger.info("%-9s %s", nazov, "OK" if ok else f"ZLYHALO ({dovod})")

        if ok:
            if s["oznameny"]:
                trva = ""
                if s.get("od"):
                    min_ = int((teraz - datetime.fromisoformat(s["od"])).total_seconds() // 60)
                    trva = f" Výpadok trval asi {min_} min."
                posli(f"Obnovené: {nazov} znova funguje.{trva}")
            s.update(zlyhani=0, oznameny=False, od=None)
            continue

        s["zlyhani"] += 1
        if s["od"] is None:
            s["od"] = teraz.isoformat()
        if s["zlyhani"] >= 2 and not s["oznameny"]:
            posli(f"Výpadok: {nazov} nefunguje ({dovod}).\n{url}")
            s["oznameny"] = True

    uloz_stav(stav)
    return 0


def _kratko(x: str, n: int = 55) -> str:
    return x if len(x) <= n else x[: n - 1] + "…"


def kontrola_odkazov() -> int:
    import firestore_client
    import http_client
    from google.cloud.firestore_v1.base_query import FieldFilter

    db = firestore_client.get_client()
    docs = list(db.collection(config.DEALS_COLLECTION)
                .where(filter=FieldFilter("status", "==", "approved")).stream())

    stav = nacitaj_stav()
    odkazy = stav.setdefault("odkazy", {})
    teraz = datetime.now(timezone.utc).isoformat()
    kontrolovane = 0
    mrtve_dnes: list[tuple[str, str, int]] = []
    ziju: set[str] = set()

    for doc in docs:
        d = doc.to_dict() or {}
        if d.get("expired") is True:
            continue
        url = d.get("sourceUrl") or d.get("url")
        if not url or not url.startswith("http"):
            continue
        # Letenky majú vlastný životný cyklus (dátum odletu).
        if "ryanair" in url or (d.get("category") == "Cestovanie" and d.get("autoGenerated")):
            continue
        kontrolovane += 1
        ziju.add(doc.id)
        if http_client.is_reachable(url, detect_soft_404=False):
            odkazy.pop(doc.id, None)
            continue
        zaznam = odkazy.setdefault(doc.id, {"dni": 0, "oznameny": False})
        zaznam["dni"] += 1
        zaznam["posledne"] = teraz
        if zaznam["dni"] >= 2 and not zaznam["oznameny"]:
            mrtve_dnes.append((doc.id, d.get("title", "?"), zaznam["dni"]))
            zaznam["oznameny"] = True

    # Záznamy o dealoch, ktoré už nie sú medzi zverejnenými, čistíme.
    for k in [k for k in odkazy if k not in ziju]:
        odkazy.pop(k, None)

    logger.info("Skontrolovaných %d dealov, mŕtvych 2 dni po sebe (nových): %d",
                kontrolovane, len(mrtve_dnes))
    if mrtve_dnes:
        riadky = [f"- {_kratko(t)}" for _id, t, _n in mrtve_dnes[:15]]
        extra = f"\n… a {len(mrtve_dnes) - 15} ďalších" if len(mrtve_dnes) > 15 else ""
        posli(f"Mŕtve odkazy ({len(mrtve_dnes)}): stránka dealu vrátila 404 dva dni po sebe.\n"
              + "\n".join(riadky) + extra
              + "\nSkontroluj v admine a deal označ ako skončený:\nhttps://henkukaj.sk/admin.html")
    uloz_stav(stav)
    return 0


def main() -> int:
    if "--odkazy" in sys.argv:
        return kontrola_odkazov()
    return kontrola_webu()


if __name__ == "__main__":
    sys.exit(main())
