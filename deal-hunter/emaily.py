"""
E-maily z vlastnej schránky (info@henkukaj.sk) cez SMTP.

Nastavenia (odosielateľ, server, port, šablóny) sú v admine
(nastavenia_admin/email). Heslo k schránke NIE JE v databáze ani
v stránke - je len v tajných nastaveniach GitHubu ako SMTP_PASSWORD
a plánovač ho dostane ako premennú prostredia.

Čo sa posiela:
  - uvítací e-mail po overení registrácie (ak je zapnutý),
  - upozornenie pre admina na novú registráciu (ak je zapnuté),
  - skúšobný e-mail z adminu.
Každý odoslaný e-mail sa zapíše do email_log - aj preto, aby uvítanie
nikto nedostal dvakrát.

Overovacie e-maily a obnovu hesla posiela Firebase sám (nastavenie
SMTP vo Firebase konzole), nie tento skript.
"""

from __future__ import annotations

import html
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("emaily")

PREDVOLENE = {
    "odosielatelMeno": "HenKukaj.sk",
    "odosielatelEmail": "noreply@henkukaj.sk",
    "smtpHost": "smtp.hostcreators.sk",
    "smtpPort": 465,
    "sifrovanie": "ssl",
    "pouzivatel": "noreply@henkukaj.sk",
    "odpovedNa": "info@henkukaj.sk",
    "uvitanieZap": False,
    "uvitaniePredmet": "Vitaj na HenKukaj.sk",
    "uvitanieText": ("Ahoj {meno},\n\nďakujeme za registráciu na HenKukaj.sk. Odteraz si môžeš ukladať dealy, "
                     "nastaviť si obľúbené letiská a odoberať novinky.\n\nNajlepšie zľavy dňa nájdeš na "
                     "https://henkukaj.sk\n\nTím HenKukaj.sk"),
    "novaRegistraciaZap": False,
    "novaRegistraciaKomu": "info@henkukaj.sk",
    "strazcaZap": True,
    "strazcaPredmet": "Našli sme deal, ktorý strážiš: {co}",
    "letenkyZap": True,
    "letenkyPredmet": "Lacná letenka z {letisko} za {cena} €",
}


def nastavenia(db) -> dict:
    try:
        d = db.document("nastavenia_admin/email").get().to_dict() or {}
    except Exception as e:
        logger.warning("Nastavenia e-mailov sa nepodarilo načítať: %s", e)
        d = {}
    return {**PREDVOLENE, **{k: v for k, v in d.items() if v not in (None, "")}}


def _html(text: str) -> str:
    """Jednoduchá HTML verzia: odseky, klikateľné odkazy, pätička."""
    import re
    bezpecne = html.escape(text)
    bezpecne = re.sub(r"(https?://[^\s<]+)", r'<a href="\1" style="color:#C44C0A">\1</a>', bezpecne)
    odseky = "".join(f'<p style="margin:0 0 14px">{o.replace(chr(10), "<br>")}</p>' for o in bezpecne.split("\n\n"))
    return f"""<!doctype html><html lang="sk"><body style="margin:0;background:#F3F5F8;padding:24px 12px;font-family:Segoe UI,Roboto,Arial,sans-serif">
<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:14px;overflow:hidden;border:1px solid #E3E7ED">
<div style="background:#E8590C;padding:16px 22px;color:#fff;font-weight:800;font-size:18px">HenKukaj.sk</div>
<div style="padding:22px;color:#2B3445;font-size:15px;line-height:1.55">{odseky}</div>
<div style="padding:14px 22px;border-top:1px solid #E3E7ED;color:#8A94A6;font-size:12px">HenKukaj.sk · info@henkukaj.sk</div>
</div></body></html>"""


def posli(n: dict, komu: str, predmet: str, text: str) -> None:
    heslo = os.environ.get("SMTP_PASSWORD", "")
    if not heslo:
        raise RuntimeError("Chýba heslo k schránke (GitHub secret SMTP_PASSWORD).")
    sprava = EmailMessage()
    sprava["From"] = formataddr((n["odosielatelMeno"], n["odosielatelEmail"]))
    sprava["To"] = komu
    sprava["Subject"] = predmet
    if n.get("odpovedNa"):
        sprava["Reply-To"] = n["odpovedNa"]
    sprava["Message-ID"] = make_msgid(domain=n["odosielatelEmail"].split("@")[-1])
    sprava.set_content(text)
    sprava.add_alternative(_html(text), subtype="html")
    port = int(n.get("smtpPort") or 465)
    kontext = ssl.create_default_context()
    if (n.get("sifrovanie") or "ssl") == "ssl":
        with smtplib.SMTP_SSL(n["smtpHost"], port, context=kontext, timeout=30) as s:
            s.login(n["pouzivatel"], heslo)
            s.send_message(sprava)
    else:
        with smtplib.SMTP(n["smtpHost"], port, timeout=30) as s:
            s.starttls(context=kontext)
            s.login(n["pouzivatel"], heslo)
            s.send_message(sprava)


def zapis(db, kluc: str | None, zaznam: dict) -> None:
    from google.cloud import firestore
    data = {**zaznam, "kedy": firestore.SERVER_TIMESTAMP}
    try:
        if kluc:
            db.collection("email_log").document(kluc).set(data)
        else:
            db.collection("email_log").add(data)
    except Exception as e:
        logger.warning("Záznam o e-maile sa nepodarilo uložiť: %s", e)


def test(db, vstup: dict) -> dict:
    """Skúšobný e-mail z adminu (úloha admin_ulohy)."""
    komu = str(vstup.get("komu") or "").strip()
    if "@" not in komu:
        raise ValueError("Zadaj platnú adresu.")
    n = nastavenia(db)
    try:
        posli(n, komu, "Skúšobný e-mail z HenKukaj.sk",
              "Ahoj,\n\ntoto je skúšobný e-mail z admin zóny HenKukaj.sk. Ak ho čítaš, odosielanie funguje.\n\nTím HenKukaj.sk")
    except Exception as e:
        zapis(db, None, {"typ": "test", "komu": komu, "ok": False, "chyba": str(e)[:300]})
        raise ValueError(f"Odoslanie zlyhalo: {e}")
    zapis(db, None, {"typ": "test", "komu": komu, "ok": True, "predmet": "Skúšobný e-mail"})
    return {"odoslane": komu}


# ── Strážca dealov a letenky ─────────────────────────────────────────
def _bez_diakritiky(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower())
                   if unicodedata.category(c) != "Mn")


def _sedi(deal: dict, strazca: dict) -> bool:
    """Všetky slová hľadaného výrazu musia byť v názve, obchode alebo popise."""
    q = _bez_diakritiky(strazca.get("q"))
    if len(q) < 2:
        return False
    text = _bez_diakritiky(f"{deal.get('title', '')} {deal.get('store', '')} {deal.get('description', '')}")
    if not all(slovo in text for slovo in q.split()):
        return False
    strop = strazca.get("cena") or 0
    if strop and (deal.get("dealPrice") or 0) > strop and not deal.get("zadarmo"):
        return False
    return True


def _odberatelia(db) -> list[tuple[str, dict]]:
    """Používatelia s overeným e-mailom - strážcov posielame len na adresy,
    o ktorých vieme, že patria svojmu majiteľovi."""
    try:
        return [(d.id, d.to_dict() or {}) for d in db.collection("users").stream()
                if (d.to_dict() or {}).get("overeny") and (d.to_dict() or {}).get("email")]
    except Exception as e:
        logger.warning("Používateľov sa nepodarilo načítať: %s", e)
        return []


def strazcovia(db, nasucho: bool = False) -> int:
    """Nové dealy porovná so strážcami ľudí a pošle e-mail. Ten istý deal
    pošle každému najviac raz (značka v email_log)."""
    import komunita

    n = nastavenia(db)
    if not n["strazcaZap"] or not os.environ.get("SMTP_PASSWORD"):
        return 0
    stav_ref = db.document("nastavenia_admin/strazcovia_stav")
    try:
        stav = stav_ref.get().to_dict() or {}
    except Exception:
        stav = {}
    od = stav.get("poslednyBeh")
    if not od:
        # Prvý beh: pozrieme len poslednú hodinu, nech nikomu nepríde
        # naraz e-mail o všetkom, čo kedy na stránke bolo.
        od = datetime.now(timezone.utc) - timedelta(hours=1)
    nove = komunita.nove_dealy_pre_strazcov(db, od)
    if not nasucho:
        from google.cloud import firestore
        stav_ref.set({"poslednyBeh": firestore.SERVER_TIMESTAMP}, merge=True)
    if not nove:
        return 0
    try:
        uz = {d.id for d in db.collection("email_log").select([]).stream()}
    except Exception:
        uz = set()
    poslane = 0
    for uid, p in _odberatelia(db):
        zoznam = [x for x in (p.get("strazcovia") or []) if isinstance(x, dict)]
        if not zoznam:
            continue
        najdene = []
        for d in nove:
            if f"strazca-{uid}-{d['id']}" in uz:
                continue
            s = next((x for x in zoznam if _sedi(d, x)), None)
            if s:
                najdene.append((d, s))
            if len(najdene) >= 5:
                break
        if not najdene:
            continue
        co = ", ".join(sorted({str(s.get("q", "")).strip() for _, s in najdene}))[:60]
        riadky = [f"Ahoj{(' ' + p['meno']) if p.get('meno') else ''},", "",
                  "našli sme dealy, ktoré si dal strážiť:", ""]
        for d, _ in najdene:
            cena = "zadarmo" if d.get("zadarmo") else (f"{float(d.get('dealPrice') or 0):.2f} €".replace(".", ","))
            povodna = f" namiesto {float(d['originalPrice']):.2f} €".replace(".", ",") if d.get("originalPrice") else ""
            riadky += [f"• {d.get('title', '')}", f"  {cena}{povodna} · {d.get('store', '')}",
                       f"  https://henkukaj.sk/?deal={d['id']}", ""]
        riadky += ["Strážcov si upravíš alebo vypneš v účte na https://henkukaj.sk", "", "Tím HenKukaj.sk"]
        if nasucho:
            logger.info("Poslal by som strážcu %s (%d dealov)", p["email"], len(najdene))
            continue
        try:
            posli(n, p["email"], n["strazcaPredmet"].replace("{co}", co), "\n".join(riadky))
            for d, _ in najdene:
                zapis(db, f"strazca-{uid}-{d['id']}", {"typ": "strazca", "komu": p["email"], "ok": True, "deal": d.get("title", "")[:80]})
            poslane += 1
        except Exception as e:
            logger.warning("Strážca pre %s zlyhal: %s", p["email"], e)
    if poslane:
        logger.info("Strážca: odoslaných %d e-mailov", poslane)
    return poslane


def letenky(db, nasucho: bool = False) -> int:
    """Lacné letenky z letísk, ktoré má človek v profile. Najviac jeden
    e-mail denne; ceny sú zo súboru letenkovej mapy."""
    import json
    from pathlib import Path

    n = nastavenia(db)
    if not n["letenkyZap"] or not os.environ.get("SMTP_PASSWORD"):
        return 0
    subor = Path(__file__).resolve().parent.parent / "assets" / "letenky" / "ceny.json"
    try:
        d = json.loads(subor.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Ceny leteniek sa nepodarilo načítať: %s", e)
        return 0
    letiska, odkial = d.get("letiska") or {}, d.get("odkial") or {}
    zaciatok = datetime.fromisoformat(d["zaciatok"]).date()
    # Najlacnejší spiatočný let na trasu (cena tam + najbližšia cesta späť
    # je zložitejšia; berieme najnižšiu cenu "tam", ako ju ukazuje mapa).
    najlacnejsie: dict[str, list] = {}
    for t in d.get("trasy") or []:
        ceny = [(c, i) for i, c in enumerate(t.get("t") or []) if c and c > 0]
        if not ceny:
            continue
        cena, i = min(ceny)
        najlacnejsie.setdefault(t["z"], []).append((cena, t["do"], zaciatok + timedelta(days=i)))
    dnes = datetime.now(timezone.utc).date().isoformat()
    try:
        uz = {x.id for x in db.collection("email_log").select([]).stream()}
    except Exception:
        uz = set()
    poslane = 0
    for uid, p in _odberatelia(db):
        strop = float(p.get("letenkyMax") or 0)
        if strop <= 0 or f"letenky-{uid}-{dnes}" in uz:
            continue
        najdene = []
        for kod in (p.get("letiska") or ["BTS"]):
            for cena, kam, den in sorted(najlacnejsie.get(kod, []))[:30]:
                if cena <= strop:
                    najdene.append((cena, kod, kam, den))
        najdene.sort()
        najdene = najdene[:6]
        if not najdene:
            continue
        prva = najdene[0]
        riadky = [f"Ahoj{(' ' + p['meno']) if p.get('meno') else ''},", "",
                  f"z tvojich letísk sme našli lety do {int(strop)} €:", ""]
        for cena, kod, kam, den in najdene:
            mesto = (letiska.get(kam) or {}).get("n", kam)
            krajina = (letiska.get(kam) or {}).get("k", "")
            riadky.append(f"• {(odkial.get(kod) or {}).get('n', kod)} → {mesto}{f' ({krajina})' if krajina else ''}"
                          f" za {cena:.2f} €".replace(".", ",") + f" · {den.day}. {den.month}.")
        riadky += ["", "Všetky lety na mape: https://henkukaj.sk/#letenky",
                   "Hranicu ceny alebo letiská si zmeníš v účte na https://henkukaj.sk", "", "Tím HenKukaj.sk"]
        predmet = (n["letenkyPredmet"].replace("{letisko}", (odkial.get(prva[1]) or {}).get("n", prva[1]))
                   .replace("{cena}", f"{prva[0]:.0f}"))
        if nasucho:
            logger.info("Poslal by som letenky %s (%d letov)", p["email"], len(najdene))
            continue
        try:
            posli(n, p["email"], predmet, "\n".join(riadky))
            zapis(db, f"letenky-{uid}-{dnes}", {"typ": "letenky", "komu": p["email"], "ok": True,
                                                "deal": f"{len(najdene)} letov do {int(strop)} €"})
            poslane += 1
        except Exception as e:
            logger.warning("Letenky pre %s zlyhali: %s", p["email"], e)
    if poslane:
        logger.info("Letenky: odoslaných %d e-mailov", poslane)
    return poslane


def spracuj_registracie(db, nasucho: bool = False) -> int:
    """
    Uvítací e-mail overeným používateľom, ktorí ho ešte nedostali, a
    upozornenie pre admina na každú novú registráciu. Beží pri každej
    kontrole plánovača (každých 5 minút).
    """
    n = nastavenia(db)
    if not (n["uvitanieZap"] or n["novaRegistraciaZap"]) or not os.environ.get("SMTP_PASSWORD"):
        return 0
    try:
        uz = {d.id for d in db.collection("email_log").select([]).stream()}
        pouzivatelia = list(db.collection("users").stream())
    except Exception as e:
        logger.warning("Registrácie sa nepodarilo načítať: %s", e)
        return 0
    poslane = 0
    for u in pouzivatelia:
        p = u.to_dict() or {}
        email = p.get("email")
        if not email:
            continue
        meno = (p.get("meno") or "").strip() or "kamarát"
        # Len registrácie od zapnutia funkcie - inak by po zapnutí dostali
        # e-mail naraz všetci doterajší používatelia.
        vytvorene = p.get("vytvorene")
        nove = lambda od: bool(od) and bool(vytvorene) and vytvorene >= od
        if n["novaRegistraciaZap"] and nove(n.get("novaRegistraciaOd")) and f"registracia-{u.id}" not in uz:
            if nasucho:
                logger.info("Upozornil by som na registráciu %s", email)
            else:
                try:
                    posli(n, n["novaRegistraciaKomu"], f"Nová registrácia: {email}",
                          f"Na HenKukaj.sk sa zaregistroval nový používateľ.\n\nE-mail: {email}\nMeno: {p.get('meno') or '–'}\n"
                          f"Newsletter: {'áno' if p.get('newsletter') else 'nie'}\n\nhttps://henkukaj.sk/admin.html#ucty")
                    zapis(db, f"registracia-{u.id}", {"typ": "nova-registracia", "komu": n["novaRegistraciaKomu"], "ok": True, "pouzivatel": email})
                    poslane += 1
                except Exception as e:
                    logger.warning("Upozornenie na registráciu zlyhalo: %s", e)
        if n["uvitanieZap"] and nove(n.get("uvitanieOd")) and p.get("overeny") and f"uvitanie-{u.id}" not in uz:
            if nasucho:
                logger.info("Poslal by som uvítanie %s", email)
                continue
            try:
                posli(n, email, n["uvitaniePredmet"], n["uvitanieText"].replace("{meno}", meno))
                zapis(db, f"uvitanie-{u.id}", {"typ": "uvitanie", "komu": email, "ok": True, "predmet": n["uvitaniePredmet"]})
                poslane += 1
            except Exception as e:
                logger.warning("Uvítací e-mail pre %s zlyhal: %s", email, e)
                zapis(db, f"uvitanie-{u.id}", {"typ": "uvitanie", "komu": email, "ok": False, "chyba": str(e)[:300]})
    if poslane:
        logger.info("Odoslaných e-mailov: %d", poslane)
    return poslane
