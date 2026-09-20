"""
Slušný HTTP klient pre scrapovanie.

Tri veci, ktoré tu robíme naschvál:
1. Predstavíme sa v User-Agent (vrátane kontaktu) — keď niekomu prekážame,
   vie nás kontaktovať namiesto toho, aby nás rovno zabanoval.
2. Držíme Crawl-delay z robots.txt (zlacnene.sk žiada 1 s, my dávame 1,5 s).
3. Rešpektujeme robots.txt — ak je URL zakázaná, nesťahujeme ju.
"""

import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

import config

logger = logging.getLogger(__name__)

# Čas posledného requestu na danú doménu — kvôli crawl-delay.
_last_request_at: dict[str, float] = {}
# Cache načítaných robots.txt, aby sme ich nesťahovali pri každej URL.
_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _domain_of(url: str) -> str:
    return urlparse(url).netloc


def _get_robots(url: str) -> urllib.robotparser.RobotFileParser | None:
    """Načíta (a nacachuje) robots.txt pre doménu danej URL."""
    parsed = urlparse(url)
    domain = parsed.netloc
    if domain in _robots_cache:
        return _robots_cache[domain]

    robots_url = f"{parsed.scheme}://{domain}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    try:
        response = requests.get(
            robots_url,
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code == 200:
            parser.parse(response.text.splitlines())
        else:
            # Žiadny robots.txt = nič nie je zakázané.
            parser.parse([])
    except requests.RequestException as e:
        logger.warning("robots.txt pre %s sa nepodarilo načítať (%s)", domain, e)
        parser = None

    _robots_cache[domain] = parser
    return parser


def is_allowed(url: str) -> bool:
    """True, ak robots.txt danej stránky dovoľuje túto URL sťahovať."""
    parser = _get_robots(url)
    if parser is None:
        # Robots.txt sa nepodarilo načítať — radšej pokračujeme, ale s pauzou.
        return True
    return parser.can_fetch(config.USER_AGENT, url)


def _respect_crawl_delay(domain: str) -> None:
    last = _last_request_at.get(domain)
    if last is not None:
        elapsed = time.monotonic() - last
        remaining = config.CRAWL_DELAY_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)
    _last_request_at[domain] = time.monotonic()


def get(url: str, *, check_robots: bool = True) -> str | None:
    """
    Stiahne stránku a vráti jej HTML. Vráti None, ak sa to nepodarí
    alebo ak robots.txt URL zakazuje.

    Jedna zlyhaná stránka nesmie zhodiť celý beh, preto tu nič nevyhadzuje.
    """
    if check_robots and not is_allowed(url):
        logger.warning("robots.txt zakazuje %s — preskakujem", url)
        return None

    domain = _domain_of(url)
    headers = {
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "sk,cs;q=0.9,en;q=0.8",
    }

    for attempt in range(1, config.HTTP_MAX_RETRIES + 1):
        _respect_crawl_delay(domain)
        try:
            response = requests.get(
                url, headers=headers, timeout=config.REQUEST_TIMEOUT_SECONDS
            )
        except requests.RequestException as e:
            logger.warning("%s: pokus %d zlyhal (%s)", url, attempt, e)
            time.sleep(attempt * 2)
            continue

        if response.status_code == 200:
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text

        # 429/503 = "spomaľ" — počkáme dlhšie a skúsime znova.
        if response.status_code in (429, 503):
            wait = attempt * 10
            logger.warning("%s: HTTP %d, čakám %ds", url, response.status_code, wait)
            time.sleep(wait)
            continue

        logger.warning("%s: HTTP %d — končím s touto URL", url, response.status_code)
        return None

    logger.error("%s: nepodarilo sa stiahnuť ani na %d. pokus", url, config.HTTP_MAX_RETRIES)
    return None


def is_reachable(url: str, detect_soft_404: bool = False) -> bool:
    """
    Overí, či odkaz vedie niekam živú. Používa sa pred zverejnením dealu
    a pri kontrole starších dealov.

    Pozor na interpretáciu: mnohé e-shopy blokujú automatické požiadavky
    a vrátia 403 aj na stránku, ktorá človeku v prehliadači funguje bez
    problému. Takú odpoveď preto NEPOVAŽUJEME za mŕtvy odkaz — inak by
    sme vyhadzovali platné dealy. Za mŕtve berieme len 404 a 410, teda
    jednoznačné "toto tu nie je".

    `detect_soft_404` rieši weby, ktoré zrušenú stránku nepošlú ako 404,
    ale presmerujú na zoznam kategórie s kódom 200. Presne to robí
    zlacnene.sk pri skončenej akcii. Keď je zapnuté, za mŕtvy sa berie aj
    odkaz, ktorý skončil na inej ceste, než sme pýtali.
    """
    from urllib.parse import urlparse

    if not url or not url.startswith("http"):
        return False

    headers = {"User-Agent": config.USER_AGENT, "Accept": "*/*"}
    domain = _domain_of(url)

    for method in ("head", "get"):
        _respect_crawl_delay(domain)
        try:
            response = requests.request(
                method, url, headers=headers,
                timeout=config.REQUEST_TIMEOUT_SECONDS, allow_redirects=True,
            )
        except requests.RequestException as e:
            logger.debug("%s: %s zlyhalo (%s)", url, method, e)
            continue

        if response.status_code in (404, 410):
            return False

        if detect_soft_404 and response.url:
            wanted = urlparse(url).path.rstrip("/").lower()
            landed = urlparse(response.url).path.rstrip("/").lower()
            if wanted and wanted != landed:
                logger.info("Mäkká 404: %s presmerovalo na %s", url, response.url)
                return False
        if response.status_code < 400 or response.status_code in (401, 403, 405, 429):
            # 405 = server nepodporuje HEAD, skúsime GET
            if response.status_code == 405 and method == "head":
                continue
            return True

    # Nepodarilo sa spojiť ani raz - radšej deal necháme, než ho zahodiť
    # kvôli výpadku siete na našej strane.
    return True
