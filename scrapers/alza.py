name: Deal Hunter - denný beh

on:
  schedule:
    # 06:30 UTC = 07:30/08:30 SK čas (podľa letného/zimného času)
    - cron: "30 6 * * *"
  workflow_dispatch: {}  # umožní aj manuálne spustenie z GitHub UI

jobs:
  run-deal-hunter:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Set up Chrome
        uses: browser-actions/setup-chrome@v1

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Write Firebase credentials
        run: echo "$FIREBASE_SERVICE_ACCOUNT" > firebase-credentials.json
        env:
          FIREBASE_SERVICE_ACCOUNT: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}

      - name: Run Deal Hunter
        run: python main.py
        env:
          FIRESTORE_PROJECT_ID: dealboard-e60bf
          MIN_DEALS_PER_DAY: "5"
          MIN_DISCOUNT_PERCENT: "15"
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}

      - name: Upload debug screenshot (ak scraper nenašiel produkty)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: debug-alza
          path: debug-alza/
          if-no-files-found: ignore

      - name: Cleanup credentials file
        if: always()
        run: rm -f firebase-credentials.json
