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
