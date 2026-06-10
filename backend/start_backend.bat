@echo off
title AlphaHunter - Backend (FastAPI :8000)
call venv\Scripts\activate.bat
uvicorn app.main:app --reload --reload-exclude "data" --reload-exclude "alphahunter.db" --reload-exclude "alphahunter.db-journal" --reload-exclude "alphahunter.db-wal" --reload-exclude "alphahunter.db-shm" --host 127.0.0.1 --port 8000
