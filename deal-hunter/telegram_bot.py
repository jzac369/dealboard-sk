"""
Schvaľovanie dealov cez Telegram.

AKO TO FUNGUJE BEZ SERVERA
Telegram bežne očakáva, že tlačidlá obslúži server s verejnou adresou
(webhook). Taký nemáme a kvôli tomuto ho nechceme prevádzkovať. Preto
používame opačný smer: Telegram si drží frontu udalostí a my sa ho raz
za čas spýtame "stalo sa niečo?" (metóda getUpdates). Pýta sa druhý
workflow (telegram-approve.yml) každých 15 minút.

Dôsledok, s ktorým treba rátať: medzi stlačením tlačidla a zmenou na
stránke ubehne až ~15 minút. Nie je to chyba, je to cena za to, že
nepotrebujeme server.

BEZPEČNOSŤ
Bot je verejne dosiahnuteľný — jeho meno vie ktokoľvek uhádnuť. Preto
prijímame príkazy VÝHRADNE od chat ID uvedeného v konfigurácii. Bez tej
kontroly by ktokoľvek mohol schvaľovať dealy na cudziu stránku.
"""

import logging
from typing import Any, Optional

import requests

import config

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot"
# Kde si pamätáme, po ktorú udalosť sme už spracovali.
STATE_COLLECTION = "agent_state"
STATE_DOCUMENT = "telegram"

_TIMEOUT = 20


def is_configured() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def _call_quietly(method: str, payload: dict) -> Optional[dict]:
    """Ako _call, ale neúspech len zaznamená do debug logu."""
    return _call(method, payload, quiet=True)


def _call(method: str, payload: dict, quiet: bool = False,
          http_timeout: Optional[int] = None) -> Optional[dict]:
    """Zavolá Telegram API. Vráti None, keď to zlyhá — nikdy nevyhodí výnimku."""
    url = f"{API_BASE}{config.TELEGRAM_BOT_TOKEN}/{method}"
    try:
        response = requests.post(url, json=payload, timeout=http_timeout or _TIMEOUT)
        data = response.json()
    except Exception as e:
        logger.log(logging.DEBUG if quiet else logging.WARNING,
                   "Telegram %s zlyhalo: %s", method, e)
        return None

    if not data.get("ok"):
        logger.log(logging.DEBUG if quiet else logging.WARNING,
                   "Telegram %s vrátil chybu: %s", method, data.get("description"))
        return None
    return data.get("result")


# ── odosielanie návrhov ───────────────────────────────────────────────

def _format_caption(deal: dict) -> str:
    # Pôvodná cena nemusí byť známa - letenky ju nemajú a pri feedoch ju
    # zdroj neuvádza. Vtedy píšeme len aktuálnu cenu; formátovať None
    # cez :.2f by spadlo na TypeError a správa by neodišla vôbec.
    povodna = deal.get("originalPrice")
    zlava = deal.get("discountPercent") or 0
    cena = f"💰 <b>{deal.get('dealPrice', 0):.2f} €</b>"
    if povodna:
        cena += f"  <s>{float(povodna):.2f} €</s>"
        if zlava:
            cena += f"  (−{zlava} %)"

    lines = [
        f"<b>{_escape(deal.get('title', ''))}</b>",
        "",
        cena,
        f"🏬 {_escape(deal.get('store', ''))}   📂 {_escape(deal.get('category', ''))}",
    ]
    if deal.get("validUntil"):
        lines.append(f"📅 Platí do {deal['validUntil']}")

    description = deal.get("description") or ""
    if description:
        lines += ["", _escape(description)]

    if deal.get("url"):
        lines += ["", f'<a href="{deal["url"]}">Otvoriť ponuku</a>']

    return "\n".join(lines)


def _escape(text: str) -> str:
    """Telegram HTML režim si vyžaduje ošetriť tri znaky."""
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def send_deal_for_approval(deal_id: str, deal: dict) -> bool:
    """Pošle jeden návrh s tlačidlami Schváliť / Zamietnuť."""
    if not is_configured():
        return False

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Schváliť", "callback_data": f"a:{deal_id}"},
            {"text": "❌ Zamietnuť", "callback_data": f"r:{deal_id}"},
        ]]
    }
    payload: dict[str, Any] = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
    }

    image = deal.get("imageUrl") or ""
    # Obrázok posielame len ak je to odkaz. Base64 by Telegram neprijal.
    if image.startswith("http"):
        payload["photo"] = image
        payload["caption"] = _format_caption(deal)
        if _call("sendPhoto", payload) is not None:
            return True
        # Keď sa obrázok nepodarí načítať, pošleme aspoň text.
        payload.pop("photo", None)
        payload["text"] = payload.pop("caption")
    else:
        payload["text"] = _format_caption(deal)

    payload["link_preview_options"] = {"is_disabled": True}
    return _call("sendMessage", payload) is not None


def send_summary(count: int) -> None:
    if not is_configured():
        return
    _call("sendMessage", {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": (
            f"🛍️ Deal Hunter našiel {count} nových návrhov.\n"
            f"Rozhodni tlačidlami nižšie, alebo v admin paneli:\n"
            f"https://henkukaj.sk/admin.html"
        ),
        "link_preview_options": {"is_disabled": True},
    })


# ── spracovanie stlačených tlačidiel ──────────────────────────────────

def _state_ref(db):
    return db.collection(STATE_COLLECTION).document(STATE_DOCUMENT)


def _load_offset(db) -> int:
    try:
        snapshot = _state_ref(db).get()
        if snapshot.exists:
            return int((snapshot.to_dict() or {}).get("offset", 0))
    except Exception as e:
        logger.warning("Offset sa nepodarilo načítať: %s", e)
    return 0


def _save_offset(db, offset: int) -> None:
    try:
        _state_ref(db).set({"offset": offset}, merge=True)
    except Exception as e:
        logger.warning("Offset sa nepodarilo uložiť: %s", e)


def _is_authorised(callback: dict) -> bool:
    """
    Prijímame len stlačenia z nášho chatu. Bot je verejne dosiahnuteľný,
    takže bez tejto kontroly by cudzí človek mohol schvaľovať dealy.
    """
    sender = str(callback.get("from", {}).get("id", ""))
    chat = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    allowed = str(config.TELEGRAM_CHAT_ID)
    return allowed in (sender, chat)


def process_updates(db, long_poll: int = 0) -> int:
    """
    Vyzdvihne stlačené tlačidlá z Telegramu a premietne ich do databázy.
    Vráti počet spracovaných rozhodnutí.

    `long_poll` zapne dlhé dopytovanie: Telegram podrží spojenie otvorené
    až tak dlho a odpovie hneď, ako niekto stlačí tlačidlo. Reakcia je
    potom okamžitá namiesto čakania na ďalší beh.
    """
    if not is_configured():
        logger.info("Telegram nie je nastavený — preskakujem.")
        return 0

    offset = _load_offset(db)
    updates = _call("getUpdates", {
        "offset": offset,
        "timeout": long_poll,
        "allowed_updates": ["callback_query"],
    }, http_timeout=long_poll + 15 if long_poll else None)
    if not updates:
        return 0

    handled = 0
    highest = offset

    for update in updates:
        highest = max(highest, update.get("update_id", 0) + 1)

        callback = update.get("callback_query")
        if not callback:
            continue

        if not _is_authorised(callback):
            logger.warning(
                "Odmietnuté stlačenie od neoprávneného používateľa %s",
                callback.get("from", {}).get("id"),
            )
            _call("answerCallbackQuery", {
                "callback_query_id": callback["id"],
                "text": "Nemáš oprávnenie.",
            })
            continue

        if _apply_decision(db, callback):
            handled += 1

    # Offset uložíme až nakoniec. Keby beh spadol uprostred, Telegram nám
    # tie isté udalosti pošle znova — radšej dvakrát než ich stratiť.
    _save_offset(db, highest)
    return handled


def _apply_decision(db, callback: dict) -> bool:
    data = callback.get("data", "")
    if ":" not in data:
        return False

    action, deal_id = data.split(":", 1)
    status = {"a": "approved", "r": "rejected"}.get(action)
    if not status:
        return False

    doc_ref = db.collection(config.DEALS_COLLECTION).document(deal_id)
    try:
        snapshot = doc_ref.get()
        if not snapshot.exists:
            answer = "Deal už neexistuje."
        elif (snapshot.to_dict() or {}).get("status") != "pending":
            # Medzitým si rozhodol v admin paneli — necháme to tak.
            answer = "O tomto deale už bolo rozhodnuté."
        else:
            doc_ref.update({"status": status})
            answer = "Schválené ✅" if status == "approved" else "Zamietnuté ❌"
            logger.info("Deal %s -> %s", deal_id, status)
    except Exception as e:
        logger.error("Rozhodnutie o deale %s zlyhalo: %s", deal_id, e)
        answer = "Nepodarilo sa, skús to v admin paneli."

    # Bublinka s potvrdením priamo v Telegrame. Skúsime ju, ale takmer
    # vždy zlyhá na "query is too old": Telegram čaká odpoveď do pár
    # sekúnd a my sa pýtame až pri ďalšom behu, teda o minúty. Je to
    # daň za riešenie bez servera, nie chyba — preto to nehlásime ako
    # varovanie. Potvrdenie používateľ aj tak uvidí na tlačidlách nižšie.
    _call_quietly("answerCallbackQuery", {
        "callback_query_id": callback["id"],
        "text": answer,
    })
    # Tlačidlá nahradíme výsledkom, aby sa nedalo kliknúť druhý raz.
    _call("editMessageReplyMarkup", {
        "chat_id": callback["message"]["chat"]["id"],
        "message_id": callback["message"]["message_id"],
        "reply_markup": {"inline_keyboard": [[{
            "text": answer,
            "callback_data": "done",
        }]]},
    })
    return True


def diagnose(db) -> dict:
    """
    Zistí, prečo sa stlačenia tlačidiel nespracúvajú.

    Vracia stav bez akýchkoľvek tajných údajov - token ani chat ID sa
    do výstupu nedostanú.
    """
    info: dict = {"nastavene": is_configured()}
    if not is_configured():
        return info

    me = _call("getMe", {})
    info["bot"] = (me or {}).get("username", "?")

    # Webhook a getUpdates sa navzájom vylučujú. Keď je nastavený
    # webhook, getUpdates vracia chybu alebo ticho nič.
    hook = _call("getWebhookInfo", {})
    if hook is not None:
        info["webhook_url"] = hook.get("url") or "(žiadny)"
        info["cakajucich_podla_telegramu"] = hook.get("pending_update_count")

    info["ulozeny_offset"] = _load_offset(db)

    # Bez offsetu uvidíme všetko, čo Telegram ešte drží.
    raw = _call("getUpdates", {"timeout": 0, "limit": 100})
    if raw is None:
        info["getUpdates"] = "zlyhalo"
    else:
        info["dostupnych_updatov"] = len(raw)
        info["typy"] = sorted({k for u in raw for k in u if k != "update_id"})
        ids = [u.get("update_id") for u in raw]
        info["rozsah_id"] = [min(ids), max(ids)] if ids else None
    return info
