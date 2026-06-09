@echo off
title AlphaHunter - Backend (FastAPI :8000)
call venv\Scripts\activate.bat
uvicorn app.main:app --reload --reload-exclude "data" --reload-exclude "alphahunter.db" --host 127.0.0.1 --port 8000
