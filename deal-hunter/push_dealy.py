"""
Push notifikácie do Android appky pri každom novom zverejnenom deale.

Appka sa pri prvom spustení prihlási na tému "dealy" (Firebase Cloud
Messaging). Plánovač každých 5 minút zavolá posli_nove(): nájde dealy,
ktoré sú zverejnené a ešte sme o nich nepísali, a pošle notifikáciu.

Zverejnenie sa deje na viacerých miestach (admin, Telegram, plánovač),
preto sa nesledujú udalosti, ale zoznam už oznámených ID v dokumente
admin_info/push. Pri prvom behu sa všetko existujúce len zapíše ako
oznámené - nikto nechce dostať 20 notifikácií naraz.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

import config

logger = logging.getLogger(__name__)

TEMA = "dealy"
MAX_NARAZ = 3
MAX_VEK = timedelta(hours=6)
PAMAT = 300


def vyber_na_odoslanie(dealy: list[tuple[str, dict]], poslane: set[str],
                       teraz: datetime) -> list[tuple[str, dict]]:
    """Najnovšie neoznámené, platné dealy zverejnené v posledných hodinách."""
    out = []
    for deal_id, d in dealy:
        if deal_id in poslane or d.get("expired") or d.get("status") != "approved":
            continue
        cas = d.get("timestamp")
        if cas is not None and teraz - cas > MAX_VEK:
            continue
        out.append((deal_id, d))
    return out[:MAX_NARAZ]


def _telo(d: dict) -> str:
    cast = []
    if d.get("zadarmo"):
        cast.append("Zadarmo")
    elif d.get("dealPrice"):
        cast.append(f"{float(d['dealPrice']):.2f} {d.get('currency') or '€'}".replace(".", ","))
    if d.get("discountPercent"):
        cast.append(f"-{int(d['discountPercent'])} %")
    if d.get("store"):
        cast.append(str(d["store"]))
    return " · ".join(cast)


def sprava(deal_id: str, d: dict) -> dict:
    """Správa len s "data": notifikáciu skladá a filtruje appka (témy, minimálna
    zľava), takže ju vie prispôsobiť nastaveniam človeka."""
    data = {
        "typ": "dealy",
        "title": (d.get("title") or "Nový deal")[:100],
        "body": _telo(d),
        "kategoria": d.get("category") or "",
        "zlava": str(int(d.get("discountPercent") or 0)),
        "url": f"https://henkukaj.sk/?deal={deal_id}",
    }
    img = d.get("imageUrl") or ""
    if img.startswith("https://"):
        data["image"] = img
    return {"message": {"topic": TEMA, "data": data, "android": {"priority": "HIGH"}}}


def posli_pouzivatelovi(p: dict, title: str, body: str, url: str) -> int:
    """Push zo Stráže ceny / letenky na zariadenia z profilu (users/{uid}.fcmTokens).
    Vráti počet odoslaných; človek, ktorý ich v appke vypol, nič nedostane."""
    tokeny = p.get("fcmTokens") or []
    if not tokeny or p.get("pushStraz") is False:
        return 0
    try:
        token, projekt = _token()
    except Exception as e:
        logger.warning("Push: prihlásenie do FCM zlyhalo: %s", e)
        return 0
    n = 0
    for t in tokeny:
        r = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{projekt}/messages:send",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": {"token": t, "android": {"priority": "HIGH"},
                              "data": {"typ": "straz", "title": title[:100], "body": body[:200], "url": url}}},
            timeout=20)
        if r.status_code == 200:
            n += 1
        else:
            logger.warning("Push používateľovi zlyhal (%s)", r.status_code)
    return n


def _token() -> tuple[str, str]:
    from google.oauth2 import service_account
    import google.auth.transport.requests as gtr
    cred = service_account.Credentials.from_service_account_file(
        config.FIREBASE_CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/firebase.messaging"])
    cred.refresh(gtr.Request())
    return cred.token, cred.project_id


def posli_nove(db, nasucho: bool = False) -> int:
    ref = db.collection("admin_info").document("push")
    snap = ref.get()
    stav = snap.to_dict() or {}
    poslane = set(stav.get("poslane") or [])

    try:
        docs = list(db.collection("deals").where("status", "==", "approved")
                    .order_by("timestamp", direction="DESCENDING").limit(20).stream())
    except Exception as e:
        logger.warning("Push: dealy sa nepodarilo načítať: %s", e)
        return 0
    dealy = [(x.id, x.to_dict() or {}) for x in docs]

    if not snap.exists:
        if not nasucho:
            ref.set({"poslane": [i for i, _ in dealy]})
        logger.info("Push: prvý beh, %d existujúcich dealov označených ako oznámené", len(dealy))
        return 0

    nove = vyber_na_odoslanie(dealy, poslane, datetime.now(timezone.utc))
    if not nove:
        return 0
    if nasucho:
        for i, d in nove:
            logger.info("Poslal by som push: %s", d.get("title"))
        return 0

    try:
        token, projekt = _token()
    except Exception as e:
        logger.warning("Push: prihlásenie do FCM zlyhalo: %s", e)
        return 0
    poslanych = 0
    for deal_id, d in nove:
        r = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{projekt}/messages:send",
            headers={"Authorization": f"Bearer {token}"},
            json=sprava(deal_id, d), timeout=20)
        if r.status_code == 200:
            poslanych += 1
            poslane.add(deal_id)
            logger.info("Push odoslaný: %s", d.get("title"))
        else:
            logger.warning("Push zlyhal (%s): %s", r.status_code, r.text[:200])
    ref.set({"poslane": list(poslane)[-PAMAT:]})
    return poslanych
