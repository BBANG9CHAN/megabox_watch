@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8

REM ------------------------------------------------
REM  Megabox event watcher - scheduled run
REM  Register THIS file in Task Scheduler.
REM  Keywords are set inside megabox_watch.py
REM ------------------------------------------------

cd /d %~dp0

REM Discord webhook URL is read from .env (copy .env.example)
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"

python megabox_watch.py >> watch.log 2>&1
