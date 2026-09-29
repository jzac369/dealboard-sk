@echo off
REM Denne stiahnutie cien zakladnych potravin z narodneho porovnavaca.
REM
REM Bezi lokalne, nie v cloude: api.cenyslovensko.sk odpoveda len zo
REM slovenskych adries a z GitHub Actions kazde volanie vyprsi.
REM
REM Spusta to planovana uloha "HenKukaj - ceny potravin" kazdych 30 minut.
REM KEDY sa ceny naozaj stiahnu, urcuje rozvrh v admin zone (--plan);
REM ked nie je na rade, skript skonci okamzite bez volania na zdroj.
REM Rucne mimo rozvrhu: tlacidlo "Spustit teraz" v admin zone, alebo
REM   python refresh_food_prices.py   (bez --plan stiahne vzdy)

cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set FIRESTORE_PROJECT_ID=dealboard-e60bf
set GOOGLE_APPLICATION_CREDENTIALS=%~dp0firebase-credentials.json

REM Absolutna cesta k Pythonu zamerne: planovana uloha nema rovnaku
REM PATH ako tvoj terminal a "python" by v nej nemusel existovat.
"C:\Users\jaros\AppData\Local\Python\pythoncore-3.14-64\python.exe" refresh_food_prices.py --plan >> "%~dp0ceny-potravin.log" 2>&1
exit /b %ERRORLEVEL%
