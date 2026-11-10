@echo off
rem Starts the API (the "backend"). Leave this window open while you use the app.
cd /d "%~dp0"
call venv\Scripts\activate
uvicorn main:app --app-dir backend --reload
pause
