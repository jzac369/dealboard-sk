"""
Ceny základných potravín z národného porovnávača cenyslovensko.sk.

PREČO PRÁVE TENTO ZDROJ
Je to štátny porovnávač a jeho dáta sú normalizované: produkt má typ
(napr. "maslo najmenej 80 % tuku"), takže porovnanie naprieč reťazcami
je poctivé - neporovnáva sa maslo s margarínom. Zároveň nesie dátum
zberu, takže vieme povedať "ceny k dnešnému dňu" a nie je to tvrdenie
naslepo.

AKO SA SPRÁVAME K CUDZIEMU SERVERU
- Sťahujeme raz denne. Ceny sa aj tak menia raz denne, častejšie by to
  bolo len zaťaženie navyše.
- Agent sa v hlavičke predstavuje aj s kontaktom, takže keď niekomu
  prekážame, vie napísať namiesto toho, aby nás potichu zablokoval.
- Obrázky sťahujeme tiež raz denne a zmenšené ich ukladáme k dátam.
  Vkladať ich na stránku priamo z ich servera by znamenalo, že našich
  návštevníkov platia oni - a fotky majú aj cez 1 MB.
"""

import base64
import io
import json
import logging
import urllib.parse
import urllib.request
from datetime import date

import config

logger = logging.getLogger(__name__)

API = "https://api.cenyslovensko.sk"
IMG = "https://img.cenyslovensko.sk"

# Košík základných potravín. Kľúč je typ produktu v porovnávači,
# hodnota je to, ako ho pomenujeme my, a ikona na karte.
BASKET: list[tuple[str, str, str]] = [
    ("ac", "Maslo",              "cheese"),
    ("u",  "Mlieko 1,5 %",       "milk"),
    ("g",  "Múka hladká",        "bowl"),
    ("bk", "Slnečnicový olej",   "bottle"),
    ("ai", "Zemiaky",            "carrot"),
    ("a",  "Chlieb",             "bread"),
    ("ae", "Vajcia",             "egg"),
    ("aj", "Cukor",              "candy"),
    ("r",  "Kuracie prsia",      "meat"),
    ("bm", "Biely jogurt",       "bowl"),
]

# IČO -> priečinok s obrázkami. Prevzaté z konfigurácie ich aplikácie.
IMAGE_DIRS = {
    "12345609": "billa", "50854402": "billa", "00151742": "billa",
    "35790164": "kaufland", "31347037": "billa", "50020188": "terno",
    "35793783": "lidl", "36183181": "labas", "12345666": "billa",
    "31321828": "tesco",
}

# Ako veľké fotky ukladáme. 160 px stačí na kartu aj na displeji s
# vysokou hustotou a jedna fotka vyjde na jednotky kilobajtov.
THUMB_PX = 160


def _headers() -> dict:
    return {
        "User-Agent": config.USER_AGENT,
        "Accept": "application/json",
    }


def _api(path: str, **params) -> dict | list:
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    request = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(request, timeout=config.REQUEST_TIMEOUT_SECONDS) as response:
        return json.load(response)


def load_vendors() -> dict[str, str]:
    """IČO -> názov reťazca."""
    try:
        return {v["companyId"]: v["vendorName"] for v in _api("/api/vendor")}
    except Exception as e:
        logger.warning("Zoznam reťazcov sa nepodarilo načítať: %s", e)
        return {}


def _thumbnail(picture: str, company_id: str) -> str | None:
    """Stiahne fotku produktu, zmenší ju a vráti ako data URL."""
    if not picture:
        return None

    if picture.startswith("http"):
        url = picture
    else:
        folder = IMAGE_DIRS.get(company_id)
        if not folder:
            return None
        url = f"{IMG}/{folder}/{picture}"

    try:
        request = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
        with urllib.request.urlopen(request, timeout=config.REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except Exception as e:
        logger.debug("Fotka %s sa nestiahla: %s", url, e)
        return None

    try:
        from PIL import Image

        image = Image.open(io.BytesIO(raw))
        image.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
        if image.mode not in ("RGB", "L"):
            # Priehľadnosť podložíme bielou - karta má biele pozadie.
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=72, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
    except Exception as e:
        logger.debug("Fotku sa nepodarilo spracovať: %s", e)
        return None


def _cheapest_per_vendor(type_id: str, vendors: dict[str, str]) -> list[dict]:
    """
    Najlacnejší kus daného typu v každom reťazci.

    Reťazce majú viac firemných IČO (Lidl vyšiel v surových dátach
    dvakrát), preto zlučujeme podľa názvu a necháme nižšiu cenu.
    """
    try:
        data = _api(
            "/api/product-prices/current-day",
            typeId=type_id, groupByVendor="true",
            onePerVendorCheapestOnly="true", size=40, page=0,
        )
    except Exception as e:
        logger.warning("Ceny pre typ %s sa nenačítali: %s", type_id, e)
        return []

    by_name: dict[str, dict] = {}
    for item in (data or {}).get("content", []):
        vendor_rows = item.get("vendors") or []
        if not vendor_rows:
            continue
        price = vendor_rows[0].get("minPrice")
        if price is None:
            continue

        name = vendors.get(item["companyId"], item["companyId"])
        details = item.get("productDetails") or {}
        row = {
            "vendor": name,
            "price": round(float(price), 2),
            "unitPrice": vendor_rows[0].get("minUnitPrice"),
            "product": (details.get("productName") or "").strip(),
            "packageSize": details.get("packageSize"),
            "unit": details.get("unit"),
            "onPromo": bool(vendor_rows[0].get("promoTo")),
            "reportDate": (item.get("reportDate") or "")[:10],
            "_picture": details.get("picture"),
            "_companyId": item.get("companyId"),
        }
        if name not in by_name or row["price"] < by_name[name]["price"]:
            by_name[name] = row

    return sorted(by_name.values(), key=lambda r: r["price"])


def build_snapshot() -> dict | None:
    """
    Zostaví prehľad cien celého košíka aj s poradím reťazcov.

    Vráti None, keď sa nepodarilo načítať nič - vtedy je lepšie nechať
    na stránke včerajšie dáta než ich prepísať prázdnymi.
    """
    vendors = load_vendors()
    items: list[dict] = []
    report_date = ""

    for type_id, label, icon in BASKET:
        rows = _cheapest_per_vendor(type_id, vendors)
        if not rows:
            logger.info("Pre '%s' neprišli žiadne ceny, vynechávam.", label)
            continue

        cheapest = rows[0]
        report_date = report_date or cheapest.get("reportDate", "")
        items.append({
            "label": label,
            "icon": icon,
            "product": cheapest["product"],
            "packageSize": cheapest.get("packageSize"),
            "unit": cheapest.get("unit"),
            "photo": _thumbnail(cheapest.get("_picture"), cheapest.get("_companyId")),
            "prices": [
                {k: v for k, v in row.items() if not k.startswith("_")}
                for row in rows[:6]
            ],
        })
        logger.info("%-18s %2d reťazcov, najlacnejšie %.2f € (%s)",
                    label, len(rows), cheapest["price"], cheapest["vendor"])

    if not items:
        logger.warning("Neprišli žiadne ceny - prehľad nebudem prepisovať.")
        return None

    return {
        "reportDate": report_date or date.today().isoformat(),
        "fetchedAt": date.today().isoformat(),
        "source": "cenyslovensko.sk",
        "items": items,
        "baskets": _basket_totals(items),
    }


def _basket_totals(items: list[dict]) -> list[dict]:
    """
    Koľko stojí celý košík v jednotlivých reťazcoch.

    Do poradia púšťame len reťazce, ktoré majú VŠETKY položky. Inak by
    vyhral ten, čo predáva najmenej vecí, čo by bolo zavádzajúce.
    """
    per_vendor: dict[str, dict[str, float]] = {}
    for item in items:
        for row in item["prices"]:
            per_vendor.setdefault(row["vendor"], {})[item["label"]] = row["price"]

    labels = {item["label"] for item in items}
    totals = [
        {"vendor": vendor, "total": round(sum(prices.values()), 2), "items": len(prices)}
        for vendor, prices in per_vendor.items()
        if set(prices) == labels
    ]
    return sorted(totals, key=lambda t: t["total"])
