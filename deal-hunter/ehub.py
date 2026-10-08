"""
Prehľad partnerského účtu eHUB (affiliate sieť) pre admin zónu.

Sumy v eHUB sú v českých korunách (CZK). Prepočítavame ich na EUR kurzom ECB
(denný referenčný kurz) a pri každej sume ostáva aj pôvodná hodnota v Kč.

Plánovač raz za hodinu stiahne cez eHUB API v3 kampane, transakcie a
odchádzajúce prekliky, zhrnie ich a uloží do admin_info/ehub. Admin
stránka (Zarábanie -> eHUB) len číta tento dokument - API kľúč sa tak
nikdy nedostane do prehliadača.

API kľúč a ID partnera sú v nastavenia_admin/ehub (zapisuje ich admin
v stránke eHUB), nie v kóde ani v GitHub repozitári.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

API = "https://api.ehub.cz/v3"
MAX_STRAN = 60          # poistka proti nekonečnému stránkovaniu (60 x 100 položiek)
INTERVAL_MINUT = 60


def _stahni(kluc: str, partner: str, cesta: str, **params) -> list:
    """Všetky stránky jedného zoznamu. Vracia zoznam položiek pod kľúčom odpovede."""
    kluc_odpovede = cesta.split("/")[-1]
    vsetko: list = []
    for strana in range(1, MAX_STRAN + 1):
        r = requests.get(f"{API}/publishers/{partner}/{cesta}",
                         params={"apiKey": kluc, "perPage": 100, "page": strana, **params}, timeout=40)
        if r.status_code == 401:
            raise ValueError("eHUB odmietol API kľúč (401) - skontroluj ho v nastaveniach eHUB.")
        r.raise_for_status()
        polozky = r.json().get(kluc_odpovede) or []
        vsetko += polozky
        if len(polozky) < 100:
            break
    return vsetko


def stav_kampane(k: dict) -> str:
    """approved / pending / declined / available - podľa skupín provízií."""
    stavy = {g.get("status") for g in (k.get("commissionGroups") or [])}
    for s in ("approved", "pending", "declined"):
        if s in stavy:
            return s
    return "available"


def zhrn_kampane(kampane: list[dict]) -> list[dict]:
    out = []
    for k in kampane:
        st = stav_kampane(k)
        provizie = [c for g in (k.get("commissionGroups") or []) for c in (g.get("commissions") or [])]
        # Najvyššia percentuálna provízia, inak najvyššia pevná.
        pct = [c["value"] for c in provizie if c.get("valueType") == "%"]
        pevna = [c["value"] for c in provizie if c.get("valueType") != "%"]
        out.append({
            "id": k.get("id"), "nazov": k.get("name"), "krajina": k.get("country"), "stav": st,
            "provizia": max(pct) if pct else (max(pevna) if pevna else None),
            "jednotka": "%" if pct else ("Kč" if pevna else ""),
            "cookie": k.get("cookieLifetime"), "feed": bool(k.get("hasFeed")),
            "kategoria": ((k.get("categories") or [{}])[0]).get("name", ""),
            "web": k.get("web"),
        })
    poradie = {"approved": 0, "pending": 1, "available": 2, "declined": 3}
    out.sort(key=lambda x: (poradie.get(x["stav"], 9), x["nazov"] or ""))
    return out


def kurz_czk() -> tuple[float, str]:
    """Koľko CZK je 1 EUR podľa ECB (denný referenčný kurz). Vráti (kurz, dátum)."""
    import re
    r = requests.get("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml", timeout=20)
    r.raise_for_status()
    m = re.search(r"currency=['\"]CZK['\"]\s+rate=['\"]([\d.]+)['\"]", r.text)
    d = re.search(r"time=['\"](\d{4}-\d{2}-\d{2})['\"]", r.text)
    if not m:
        raise ValueError("ECB nevrátila kurz CZK")
    return float(m.group(1)), (d.group(1) if d else "")


def _eur(czk: float, kurz: float) -> float:
    return round(czk / kurz, 2)


def zhrn_transakcie(transakcie: list[dict], nazvy: dict[str, str], kurz: float) -> dict:
    """Súčty podľa stavu, kampane a mesiaca + posledné transakcie.
    Vstupné sumy sú v CZK; výstup má pri každej sume EUR (hlavná) aj Kč."""
    def prazdne():
        return {"pocet": 0, "provizia": 0.0, "trzby": 0.0}

    stavy: dict[str, dict] = defaultdict(prazdne)
    kampane: dict[str, dict] = defaultdict(prazdne)
    mesiace: dict[str, float] = defaultdict(float)
    vyplatene = nevyplatene = 0.0

    def dvojica(d: dict) -> dict:
        return {"pocet": d["pocet"], "provizia": _eur(d["provizia"], kurz), "proviziaCzk": round(d["provizia"], 2),
                "trzby": _eur(d["trzby"], kurz), "trzbyCzk": round(d["trzby"], 2)}

    for t in transakcie:
        prov = float(t.get("commission") or 0)
        suma = float(t.get("amount") or 0)
        st = t.get("status") or "?"
        for cielovy in (stavy[st],):
            cielovy["pocet"] += 1
            cielovy["provizia"] += prov
            cielovy["trzby"] += suma
        if st != "declined":
            k = kampane[t.get("campaignId") or "?"]
            k["pocet"] += 1
            k["provizia"] += prov
            k["trzby"] += suma
            mesiace[(t.get("dateInserted") or "")[:7]] += prov
        if st == "approved":
            if t.get("payoutStatus") == "paid":
                vyplatene += prov
            else:
                nevyplatene += prov
    najnovsie = sorted(transakcie, key=lambda t: t.get("dateInserted") or "", reverse=True)[:200]
    return {
        "stavy": {k: dvojica(v) for k, v in stavy.items()},
        "kampane": [{"id": k, "nazov": nazvy.get(k, k), **dvojica(v)}
                    for k, v in sorted(kampane.items(), key=lambda kv: -kv[1]["provizia"])],
        "mesiace": {m: {"eur": _eur(v, kurz), "czk": round(v, 2)} for m, v in sorted(mesiace.items()) if m},
        "vyplatene": _eur(vyplatene, kurz), "vyplateneCzk": round(vyplatene, 2),
        "schvaleneNevyplatene": _eur(nevyplatene, kurz), "schvaleneNevyplateneCzk": round(nevyplatene, 2),
        "posledne": [{"datum": (t.get("dateInserted") or "")[:16].replace("T", " "),
                      "kampan": nazvy.get(t.get("campaignId"), t.get("campaignId")),
                      "objednavka": t.get("orderId"),
                      "suma": _eur(float(t.get("amount") or 0), kurz), "sumaCzk": round(float(t.get("amount") or 0), 2),
                      "provizia": _eur(float(t.get("commission") or 0), kurz),
                      "proviziaCzk": round(float(t.get("commission") or 0), 2),
                      "stav": t.get("status"), "vyplata": t.get("payoutStatus")} for t in najnovsie],
    }


def zhrn_kliky(kliky: list[dict], nazvy: dict[str, str], dni: int = 30) -> dict:
    """Prekliky za posledných `dni` dní (pole s dátumom sa hľadá tolerantne)."""
    od = (datetime.now(timezone.utc) - timedelta(days=dni)).date().isoformat()
    po_dnoch: Counter = Counter()
    po_kampani: Counter = Counter()
    for k in kliky:
        cas = next((str(v) for key, v in k.items() if "date" in key.lower() and v), "")
        den = cas[:10]
        if den and den < od:
            continue
        po_dnoch[den or "?"] += 1
        po_kampani[nazvy.get(k.get("campaignId"), k.get("campaignId") or "?")] += 1
    return {"spolu": sum(po_dnoch.values()), "poDnoch": dict(sorted(po_dnoch.items())),
            "poKampani": [{"nazov": n, "pocet": c} for n, c in po_kampani.most_common(15)]}


def nastavenia(db) -> dict:
    return db.document("nastavenia_admin/ehub").get().to_dict() or {}


def obnov(db, nasucho: bool = False, force: bool = False) -> dict | None:
    """Stiahne a uloží prehľad. Bez kľúča nič nerobí. Zlyhanie uloží ako chybu
    (admin ju uvidí), starý prehľad ostane."""
    from google.cloud import firestore

    n = nastavenia(db)
    kluc, partner = (n.get("apiKey") or "").strip(), (n.get("publisherId") or "0506c0ea").strip()
    if not kluc:
        return None
    ref = db.document("admin_info/ehub")
    if not force:
        try:
            posledne = (ref.get().to_dict() or {}).get("aktualizovane")
        except Exception:
            posledne = None
        if posledne and datetime.now(timezone.utc) - posledne < timedelta(minutes=INTERVAL_MINUT):
            return None
    if nasucho:
        logger.info("Obnovil by som prehľad eHUB")
        return None
    try:
        kampane = _stahni(kluc, partner, "campaigns")
        transakcie = _stahni(kluc, partner, "transactions")
        try:
            kliky = _stahni(kluc, partner, "outboundClicks")
        except Exception as e:
            logger.warning("eHUB: prekliky sa nepodarilo načítať (%s)", e)
            kliky = []
        zh = zhrn_kampane(kampane)
        nazvy = {k["id"]: k["nazov"] for k in zh}
        try:
            kurz, kurz_den = kurz_czk()
        except Exception as ex:
            # Bez čerstvého kurzu použijeme posledný známy; úplne bez kurzu sa nepočíta.
            stary = ref.get().to_dict() or {}
            kurz, kurz_den = stary.get("kurz"), stary.get("kurzDen")
            if not kurz:
                raise ValueError(f"Kurz CZK/EUR sa nepodarilo zistiť ({ex})")
            logger.warning("eHUB: kurz ECB zlyhal, používam posledný známy %s z %s", kurz, kurz_den)
        data = {
            "aktualizovane": firestore.SERVER_TIMESTAMP, "chyba": None, "partner": partner,
            "kurz": kurz, "kurzDen": kurz_den, "mena": "CZK",
            "kampane": zh, "kampaniSpolu": len(zh),
            "kampaniPodlaStavu": dict(Counter(k["stav"] for k in zh)),
            "transakcie": zhrn_transakcie(transakcie, nazvy, kurz), "kliky": zhrn_kliky(kliky, nazvy),
        }
        ref.set(data)
        logger.info("eHUB: %d kampaní, %d transakcií, %d preklikov", len(zh), len(transakcie), len(kliky))
        return {"kampani": len(zh), "transakcii": len(transakcie), "preklikov": len(kliky)}
    except Exception as e:
        # Text chyby nesmie obsahovať kľúč (je v adrese požiadavky).
        text = str(e).replace(kluc, "***")[:300]
        logger.warning("eHUB zlyhal: %s", text)
        ref.set({"chyba": text, "chybaKedy": firestore.SERVER_TIMESTAMP}, merge=True)
        return None
