# HenKukaj Deal Hunter

Agent, ktorý 3× denne prehľadá zdroje zliav, vyberie tie najlepšie a zapíše ich
na **henkukaj.sk ako návrhy čakajúce na schválenie**. Nič sa nezverejní samo —
posledné slovo máš vždy ty v admin paneli.

```
[GitHub Actions cron - 3x denne]
         │
         ▼
     main.py ─── zdroje ──▶ filtrovanie ──▶ deduplikácia ──▶ výber
         │
         ▼
  Firestore: deals (status "pending")
         │
         ▼
  https://henkukaj.sk/admin.html  ──▶  TY schvaľuješ ✅ / zamietaš ❌
         │
         ▼
  status "approved" = deal je živý na stránke
```

Agent žije v podpriečinku `deal-hunter/` repozitára so stránkou. Workflow
je v `.github/workflows/deal-hunter.yml` v koreni repozitára (inde ho
GitHub Actions nenájde).

## Rýchly štart

```bash
cd deal-hunter
pip install -r requirements-dev.txt
DRY_RUN=true python main.py
```

`DRY_RUN=true` vypíše, čo by agent pridal, ale nesiahne na databázu ani
nepotrebuje Firebase kľúč. Toto je najrýchlejší spôsob, ako zistiť, či
zdroje ešte fungujú.

## Nasadenie (jednorazovo)

### 1. Firebase service account

1. Firebase Console → Project settings → **Service accounts**
2. *Generate new private key* → stiahne sa JSON súbor
3. V GitHub repozitári: Settings → Secrets and variables → Actions → *New repository secret*
   - Názov: `FIREBASE_SERVICE_ACCOUNT`
   - Hodnota: **celý obsah** stiahnutého JSON súboru

Service account obchádza Firestore security rules, takže kvôli agentovi
netreba meniť `firestore.rules`.

> ⚠️ Ten JSON súbor je kľúč od databázy. Nikdy ho nedávaj do repozitára —
> `.gitignore` ho už blokuje, ale pozor pri kopírovaní medzi priečinkami.

### 2. Voliteľné secrets

| Secret | Na čo je |
|---|---|
| `FEED_URLS` | Affiliate feedy oddelené čiarkami. Bez neho beží len zlacnene.sk. |
| `TELEGRAM_BOT_TOKEN` | Notifikácia „čaká N nových návrhov". |
| `TELEGRAM_CHAT_ID` | Kam tú notifikáciu poslať. |

### 3. Prvé spustenie

GitHub → Actions → *Deal Hunter* → **Run workflow**. Zaškrtni `dry_run`,
aby si najprv videl, čo by pridal, bez zápisu do databázy.

## Zdroje

### `zlacnene` — zlacnene.sk (zapnuté)

Akciový tovar z letákov reťazcov (BILLA, Tesco, Kaufland, Lidl…). Pokrýva
naraz **potraviny aj letáky**, čo je pôvodná téma Hen Kukaj.

Stránka používa **schema.org microdata** (`itemprop="price"`, `"seller"`,
`"image"`) — to je strojovo čitateľný kontrakt, ktorý prežije redizajn oveľa
lepšie než CSS triedy. Preto je tento parser podstatne odolnejší než bežný
scraper.

robots.txt to dovoľuje a žiada `Crawl-delay: 1` — držíme 1,5 s.

### `feeds` — affiliate produktové feedy (treba nastaviť)

Najlepší zdroj, keď doň doplníš svoje Dognet feedy: dáta sú štruktúrované,
nerozbijú sa, a odkazy sú rovno affiliate (teda zarábajú).

Nastav cez secret `FEED_URLS`:

```
FEED_URLS=https://partner1.sk/feed.xml?a_aid=TVOJE_ID,https://partner2.sk/heureka.xml
```

Rozpozná sa automaticky:
- **Google Merchant / RSS** (`<g:price>`, `<g:sale_price>`)
- **Heureka XML** (`<SHOPITEM><PRICE_VAT>`)

Položka bez pôvodnej *aj* akciovej ceny sa zahadzuje — bez zľavy by z nej
na deal stránke bola karta s „-0 %".

### Prečo tam nie je Alza

Alza aktívne blokuje prístup z dátových centier. Pri overovaní vrátila
anti-bot stránku aj na obyčajný `robots.txt`. Keďže GitHub Actions beží
presne na takých IP adresách, scraper by v praxi nikdy nič nenašiel.
Alza je dostupná cez Dognet — cestou feedu, nie scrapovania.

## Údržba

Scraper cudzej stránky sa raz za čas rozbije. To nie je chyba v kóde,
je to normálny životný cyklus.

**Ako zistíš, že sa niečo pokazilo:** beh v Actions skončí s `Spolu nájdených: 0`,
alebo neprejdú testy.

**Ako to opravíš:**

```bash
# 1. Stiahni aktuálnu podobu stránky ako novú fixture
curl -A "HenKukajDealHunter/1.0" https://www.zlacnene.sk/akciovy-tovar/ \
  -o tests/fixtures/zlacnene_akciovy_tovar.html

# 2. Pozri, či testy prejdú
python -m pytest tests/ -v
```

Ak neprejdú, zmenila sa štruktúra stránky a treba upraviť
`scrapers/zlacnene.py` (metóda `_parse_product`). Testy ti presne povedia,
ktoré pole sa prestalo ťahať.

## Pridanie nového zdroja

1. Vytvor `scrapers/novy_zdroj.py`, trieda dedí z `BaseScraper`
2. Implementuj `fetch_candidates() -> list[DealCandidate]`
3. Zaregistruj v `scrapers/__init__.py` do `AVAILABLE_SCRAPERS`
4. Pridaj jeho názov do `ENABLED_SCRAPERS`

Filtrovanie, deduplikácia aj výber fungujú univerzálne — nič iné netreba.

Parsovanie oddeľ od sťahovania (ako v `zlacnene.py`: `fetch_candidates()`
sťahuje, `parse_listing()` parsuje), aby sa dalo testovať offline na
uloženom HTML bez zaťažovania cudzieho servera.

## Nastavenia

Všetko cez premenné prostredia — pozri `config.py`.

| Premenná | Default | Čo robí |
|---|---|---|
| `MIN_DISCOUNT_PERCENT` | 25 | Menšia zľava sa ignoruje. |
| `MAX_DISCOUNT_PERCENT` | 95 | Väčšia zľava = pravdepodobne chyba v dátach. |
| `MIN_DEAL_PRICE` | 0.50 | Odfiltruje „zľavu 50 %" na položke za 20 centov. |
| `MAX_DEALS_PER_RUN` | 12 | Aby ťa schvaľovanie nezahltilo. |
| `MAX_PER_STORE` | 4 | Aby výber nevyzeral ako leták jediného reťazca. |
| `DEDUPE_LOOKBACK_DAYS` | 30 | Ako ďaleko dozadu hľadať duplicity. |
| `ZLACNENE_MAX_PAGES` | 3 | 20 položiek na stranu. |
| `ENABLED_SCRAPERS` | `zlacnene,feeds` | Ktoré zdroje sú zapnuté. |
| `DRY_RUN` | `false` | `true` = nezapisovať, len vypísať. |

## Ako sa predchádza duplicitám

Deduplikuje sa podľa `dedupeKey` = *obchod + názov bez diakritiky + cena*,
nie podľa URL. Ten istý produkt má na rôznych zdrojoch rôzne URL, takže
deduplikácia podľa URL by nezachytila nič.

Porovnáva sa voči:
- dealom čakajúcim na schválenie (`pending`),
- **zamietnutým dealom** (`rejected`) — keď nejaký návrh odmietneš,
  agent ti ho nemá o tri hodiny ponúknuť znova,
- dealom publikovaným za posledných 30 dní.

## Čo agent zámerne nerobí

- **Nezverejňuje sám.** Všetko ide ako `status: "pending"`.
- **Nemaže ani neupravuje** existujúce dealy.
- **Neobchádza robots.txt.** Ak stránka URL zakáže, preskočí ju.
- **Nescrapuje bez identifikácie.** V User-Agent je kontaktný e-mail.
