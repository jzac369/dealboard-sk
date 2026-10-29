"""
Panel HenKukaj pre domáci server (karta „HenKukaj" v prehľade servera).

ČO ROBÍ
- Ukazuje stav agenta: posledné behy, koľko kandidátov našiel, čo prešlo
  trhovou kontrolou a prečo ostatné nie.
- Upravuje nastavenia agenta. Zapisujú sa do databázy (settings/agent), teda
  na to isté miesto, ktoré číta agent v GitHube aj admin na webe. Nastavenia
  sú tak len na jednom mieste.
- Spúšťa úlohy servera (lov, záloha, sledovanie cien...) a ukazuje ich logy.

BEZPEČNOSŤ
- Počúva len na 127.0.0.1. Z domácej siete je dostupný cez prehľad servera
  (nusmon), ktorý požiadavky na /hk/ preposiela sem.
- Každá zmena (nastavenia, spustenie úlohy) vyžaduje PIN prehľadu servera.
  PIN sa overuje rovnako ako v prehľade (PBKDF2 z ~/nusmon/config.json),
  panel ho nikde neukladá.
- Tajné nastavenia (adresy feedov s partnerským ID) sa nezobrazujú.

SPUSTENIE
  ~/bin/hk-run.sh panel/panel.py        (port 8778, len localhost)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PRIECINOK = Path(__file__).resolve().parent
sys.path.insert(0, str(PRIECINOK.parent))

import config  # noqa: E402

PORT = int(os.environ.get("HK_PANEL_PORT", "8778"))
HOME = Path.home()
PIN_SUBOR = HOME / "nusmon" / "config.json"
HK_RUN = str(HOME / "bin" / "hk-run.sh")

# Úlohy, ktoré panel vie spustiť: názov -> (popis, príkaz, log, cron čas)
ULOHY = {
    "lov": ("Lov dealov z obchodov (lekárne, elektro)", ["env", "NUC_LOV=true", "timeout", "3300", HK_RUN, "main.py"],
            "lov-nuc.log", "7:50 a 18:50"),
    "zaloha": ("Záloha databázy", [HK_RUN, "zaloha_firestore.py"], "zaloha.log", "3:30"),
    "sledovanie": ("Sledovanie cien zverejnených dealov", ["timeout", "3000", HK_RUN, "sledovanie_cien.py"],
                   "sledovanie-cien.log", "4:50"),
    "odkazy": ("Kontrola mŕtvych odkazov", [HK_RUN, "monitor.py", "--odkazy"], "monitor.log", "4:30"),
    "potraviny": ("Ceny potravín (cenyslovensko.sk)", [HK_RUN, "refresh_food_prices.py"], "ceny-potravin.log",
                  "podľa rozvrhu (každých 30 min kontrola)"),
}

_db = None


def db():
    global _db
    if _db is None:
        import firestore_client
        _db = firestore_client.get_client()
    return _db


def _json_safe(v):
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).isoformat()
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_json_safe(x) for x in v]
    return v


def over_pin(pin: str) -> bool:
    try:
        c = json.loads(PIN_SUBOR.read_text(encoding="utf-8"))
        h = hashlib.pbkdf2_hmac("sha256", str(pin).encode(), bytes.fromhex(c["salt"]), 100_000).hex()
        return hmac.compare_digest(h, c["pin_hash"])
    except Exception:
        return False


def chvost(meno: str, riadkov: int = 14) -> dict:
    p = HOME / meno
    if not p.exists():
        return {"riadky": [], "zmenene": None}
    with open(p, "rb") as f:
        try:
            f.seek(-24000, os.SEEK_END)
        except OSError:
            f.seek(0)
        text = f.read().decode("utf-8", "ignore")
    return {"riadky": text.splitlines()[-riadkov:], "zmenene": datetime.fromtimestamp(p.stat().st_mtime).isoformat()}


def bezi(uloha: str) -> bool:
    cmd = ULOHY[uloha][1]
    vzor = " ".join(x for x in cmd if x.endswith(".py") or x.startswith("--"))
    if uloha == "lov":
        vzor = "main.py"
    try:
        out = subprocess.run(["pgrep", "-f", vzor], capture_output=True, text=True).stdout.split()
        return any(int(pid) != os.getpid() for pid in out)
    except Exception:
        return False


def zalohy() -> list[dict]:
    koren = HOME / "zalohy"
    if not koren.exists():
        return []
    out = []
    for d in sorted(koren.iterdir(), reverse=True)[:5]:
        if d.is_dir():
            velkost = sum(f.stat().st_size for f in d.glob("*")) / 1_048_576
            out.append({"den": d.name, "mb": round(velkost, 1), "suborov": len(list(d.glob("*")))})
    return out


def predvolene() -> dict:
    p = dict(config.PREDVOLENE)
    p.update({"trhKontrola": True, "trhMinObchodov": config.TRH_MIN_OBCHODOV,
              "trhTolerancia": config.TRH_TOLERANCIA, "trhMaxKontrol": config.TRH_MAX_KONTROL})
    return p


def stav() -> dict:
    d = db()
    nastavenia = d.document("settings/agent").get().to_dict() or {}
    rozvrh = (d.document("settings/schedule").get().to_dict() or {}).get("jobs", {})
    behy = {k: (d.document(f"admin_info/{k}").get().to_dict() or {}) for k in ("agent_beh", "lov_server_beh")}
    obchody = (d.document("nastavenia_admin/sitemap_obchody_nuc").get().to_dict() or {}).get("obchody", [])
    from google.cloud.firestore_v1.base_query import FieldFilter
    cakajuce = len(list(d.collection(config.DEALS_COLLECTION)
                        .where(filter=FieldFilter("status", "==", "pending")).select([]).stream()))
    from scrapers import AVAILABLE_SCRAPERS
    return _json_safe({
        "nastavenia": nastavenia, "predvolene": predvolene(), "zdrojeMozne": sorted(AVAILABLE_SCRAPERS),
        "rozvrh": rozvrh, "behy": behy, "cakajuce": cakajuce,
        "obchody": [{"domena": o.get("domena"), "zap": o.get("zap", True), "strana": o.get("strana"),
                     "sitemapy": o.get("sitemapy", [])} for o in obchody],
        "ulohy": {k: {"popis": v[0], "cas": v[3], "bezi": bezi(k), "log": chvost(v[2])} for k, v in ULOHY.items()},
        "zalohy": zalohy(), "cas": datetime.now().isoformat(),
    })


def over_nastavenia(vstup: dict) -> tuple[dict, list[str]]:
    """Prepustí len známe kľúče s rozumnými hodnotami (rovnaké hranice ako agent)."""
    from scrapers import AVAILABLE_SCRAPERS
    ok, chyby = {}, []
    for kluc, (_premenna, dole, hore) in config._CISLA.items():
        if kluc in vstup:
            try:
                v = float(vstup[kluc])
            except (TypeError, ValueError):
                chyby.append(f"{kluc}: nie je číslo"); continue
            if not dole <= v <= hore:
                chyby.append(f"{kluc}: musí byť {dole} až {hore}"); continue
            # Celé čísla ostanú celé (agent ich tak aj očakáva), podiely sú desatinné.
            ok[kluc] = int(v) if isinstance(getattr(config, _premenna), int) else v
    for kluc in config._ZOZNAMY:
        if kluc in vstup:
            v = vstup[kluc]
            if isinstance(v, str):
                v = [x.strip() for x in v.split(",")]
            if not isinstance(v, list):
                chyby.append(f"{kluc}: má byť zoznam"); continue
            ok[kluc] = [str(x).strip() for x in v if str(x).strip()][:50]
    if "trhKontrola" in vstup:
        ok["trhKontrola"] = bool(vstup["trhKontrola"])
    if "zdroje" in vstup:
        z = [str(x) for x in (vstup["zdroje"] or []) if str(x) in AVAILABLE_SCRAPERS]
        if z:
            ok["zdroje"] = z
        else:
            chyby.append("zdroje: aspoň jeden zdroj musí ostať zapnutý")
    return ok, chyby


def uloz_nastavenia(zmeny: dict) -> None:
    from google.cloud import firestore
    d = db()
    d.document("settings/agent").set({**zmeny, "upravil": "panel servera",
                                      "upravene": firestore.SERVER_TIMESTAMP}, merge=True)
    d.collection("audit_log").add({"dealId": None, "action": "nastavenia-agenta",
                                   "detail": "Panel servera: " + ", ".join(f"{k}={v}" for k, v in zmeny.items())[:900],
                                   "by": "panel", "timestamp": firestore.SERVER_TIMESTAMP})


def uloz_obchody(obchody: list) -> list[str]:
    chyby, cisty = [], []
    for o in obchody or []:
        dom = str(o.get("domena") or "").strip().lower().removeprefix("www.")
        sm = [u.strip() for u in (o.get("sitemapy") or []) if str(u).strip().startswith("https://")]
        if not dom or not sm:
            chyby.append(f"{dom or '?'}: chýba doména alebo sitemapa (https://)"); continue
        z = {"domena": dom, "sitemapy": sm[:10], "zap": bool(o.get("zap", True)), "id": f"panel-{dom}"}
        try:
            n = int(o.get("strana") or 40)
            z["strana"] = max(1, min(300, n))
        except (TypeError, ValueError):
            z["strana"] = 40
        cisty.append(z)
    if not chyby:
        db().document("nastavenia_admin/sitemap_obchody_nuc").set({"obchody": cisty}, merge=True)
    return chyby


def spusti(uloha: str) -> tuple[bool, str]:
    if uloha not in ULOHY:
        return False, "neznáma úloha"
    if bezi(uloha):
        return False, "úloha už beží"
    _popis, cmd, log, _cas = ULOHY[uloha]
    with open(HOME / log, "ab") as f:
        f.write(f"\n=== spustené z panelu {datetime.now():%d.%m.%Y %H:%M} ===\n".encode())
        subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(PRIECINOK.parent),
                         start_new_session=True)
    return True, "spustené"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def poslat(self, body, kod=200, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(kod)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urlparse(self.path).path.rstrip("/") or "/"
        if p in ("/", "/index.html"):
            return self.poslat((PRIECINOK / "index.html").read_bytes(), ctype="text/html; charset=utf-8")
        if p == "/api/stav":
            try:
                return self.poslat(stav())
            except Exception as e:
                return self.poslat({"chyba": str(e)}, 500)
        self.poslat({"chyba": "nenájdené"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path.rstrip("/")
        try:
            n = int(self.headers.get("Content-Length", "0") or 0)
            body = json.loads(self.rfile.read(min(n, 200_000)) or b"{}")
        except Exception:
            return self.poslat({"ok": False, "sprava": "zlé dáta"}, 400)
        if not over_pin(body.get("pin", "")):
            time.sleep(1)
            return self.poslat({"ok": False, "sprava": "nesprávny PIN"}, 403)
        try:
            if p == "/api/nastavenia":
                zmeny, chyby = over_nastavenia(body.get("nastavenia") or {})
                if chyby:
                    return self.poslat({"ok": False, "sprava": "; ".join(chyby)}, 400)
                if zmeny:
                    uloz_nastavenia(zmeny)
                return self.poslat({"ok": True, "sprava": f"uložené ({len(zmeny)} hodnôt)"})
            if p == "/api/obchody":
                chyby = uloz_obchody(body.get("obchody"))
                return self.poslat({"ok": not chyby, "sprava": "; ".join(chyby) or "uložené"}, 400 if chyby else 200)
            if p == "/api/spustit":
                ok, sprava = spusti(str(body.get("uloha", "")))
                return self.poslat({"ok": ok, "sprava": sprava}, 200 if ok else 409)
        except Exception as e:
            return self.poslat({"ok": False, "sprava": f"chyba: {e}"}, 500)
        self.poslat({"ok": False, "sprava": "nenájdené"}, 404)


if __name__ == "__main__":
    print(f"Panel HenKukaj na 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
