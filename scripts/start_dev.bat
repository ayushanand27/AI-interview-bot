@echo off
REM Cross-network dev: start ngrok tunnels and update .env (see start_dev.py)
cd /d "%~dp0.."
python scripts\start_dev.py
pause
