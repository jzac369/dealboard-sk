@echo off
REM Ranne hladanie lacnych leteniek Ryanair z Bratislavy.
REM Vysledok chodi do Telegramu, na stranku sa nic nezapisuje.
REM
REM Spusta to planovana uloha "HenKukaj - letenky".
REM Rucne:  letenky.cmd

cd /d "%~dp0"

REM Token bota je v samostatnom subore, ktory je v .gitignore a do
REM repozitara sa nikdy nedostane. Sablonu mas v telegram.env.cmd.vzor
REM - skopiruj ju na telegram.env.cmd a doplnaj do nej hodnoty.
if not exist "%~dp0telegram.env.cmd" (
  echo CHYBA: chyba subor telegram.env.cmd s tokenom bota.
  echo Skopiruj telegram.env.cmd.vzor na telegram.env.cmd a vypln ho.
  exit /b 2
)
call "%~dp0telegram.env.cmd"

REM Nevyplneny subor je castejsia chyba nez chybajuci. Bez tejto
REM kontroly by skript dobehol az po Telegram, ten by odmietol token
REM a v logu by bola len nejasna hlaska o zlyhanom odoslani.
echo %TELEGRAM_BOT_TOKEN% | find "sem_pride" >nul
if not errorlevel 1 (
  echo CHYBA: v telegram.env.cmd su este zastupne hodnoty zo vzoru.
  echo Otvor ho a doplnaj skutocny token bota a chat id.
  exit /b 3
)
if "%TELEGRAM_CHAT_ID%"=="" (
  echo CHYBA: v telegram.env.cmd chyba TELEGRAM_CHAT_ID.
  exit /b 3
)

REM Absolutna cesta k Pythonu zamerne: planovana uloha nema rovnaku
REM PATH ako tvoj terminal a "python" by v nej nemusel existovat.
"C:\Users\jaros\AppData\Local\Python\pythoncore-3.14-64\python.exe" ryanair_letenky.py >> "%~dp0letenky.log" 2>&1
exit /b %ERRORLEVEL%
