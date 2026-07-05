# henkukaj.sk – Deal Hunter agent

Automatizovaný denný scraper, ktorý nájde najlepšie zľavy a zapíše ich do
Firestore kolekcie `pending_deals`, odkiaľ ich schvaľuješ v admin paneli.

## Nastavenie (jednorazovo)

### 1. Firebase service account
1. Choď do Firebase Console → Project settings → Service accounts
2. "Generate new private key" → stiahne sa JSON súbor
3. Skopíruj **celý obsah** tohto JSON súboru
4. V GitHub repo: Settings → Secrets and variables → Actions → New repository secret
   - Name: `FIREBASE_SERVICE_ACCOUNT`
   - Value: (vlož celý JSON obsah)

### 2. Firestore Security Rules
Service account obchádza bežné security rules (má admin prístup), takže
netreba meniť existujúce pravidlá pre verejný prístup.

### 3. (voliteľné) Telegram notifikácie
Ak chceš dostávať správu keď pribudnú nové návrhy:
- `TELEGRAM_BOT_TOKEN` a `TELEGRAM_CHAT_ID` ako ďalšie GitHub Secrets
  (rovnaký princíp ako pri Magna Job Monitor bote)

### 4. Test lokálne (pred prvým ostrým behom)
```bash
pip install -r requirements.txt
export FIREBASE_CREDENTIALS_PATH=./moj-lokalny-kluc.json
export FIRESTORE_PROJECT_ID=dealboard-e60bf
python main.py
```

## Dôležitá poznámka k Alza scraperu

Alza si štruktúru HTML stránky občas mení. Ak scraper po čase prestane
nachádzať produkty (log ukáže "nájdených 0 produktových kariet"):

1. Otvor https://www.alza.sk/vypredaj-akcia-zlava/e0.htm v prehliadači
2. Pravý klik na produktovú kartu → Preskúmať (Inspect)
3. Nájdi aktuálnu CSS triedu obalu karty, názvu, ceny a starej ceny
4. Uprav selektory v `scrapers/alza.py` (funkcia `_parse_item`)

Toto je bežná údržba pri akomkoľvek scraperi — nie chyba v kóde.

## Pridanie ďalšieho zdroja

1. Vytvor `scrapers/nazov_zdroja.py`, trieda dedí z `BaseScraper`
2. Implementuj `fetch_candidates()` → vráti `list[DealCandidate]`
3. Zaregistruj v `scrapers/__init__.py` do `ALL_SCRAPERS`

Žiadne iné zmeny netreba — `main.py` aj deduplikácia fungujú univerzálne.

## Ako to zapadá do celého systému

```
[GitHub Actions cron - denne]
        │
        ▼
  main.py (tento projekt)
        │
        ▼
  Firestore: pending_deals
        │
        ▼
  Admin panel (henkukaj.sk) — TY schvaľuješ ✅ / zamietaš ❌
        │
        ▼
  Firestore: deals (live na stránke)
        │
        ├──▶ [ĎALŠÍ KROK] SEO generátor statických stránok
        └──▶ [ĎALŠÍ KROK] Facebook auto-post
```

Tieto dva posledné kroky (SEO + FB) nadviažeme na moment schválenia dealu
v admin paneli — pripravím ich v ďalšom kroku.
