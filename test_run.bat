@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8

REM ------------------------------------------------
REM  One-shot notification test.
REM  Clears history and sends every matching event
REM  so you can check Discord / phone push.
REM ------------------------------------------------

cd /d %~dp0

REM Discord webhook URL is read from .env (copy .env.example)
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
set FIRST_RUN_NOTIFY=1

if exist seen_events.json del seen_events.json

python megabox_watch.py

echo.
echo --- test finished. check your Discord channel. ---
pause
