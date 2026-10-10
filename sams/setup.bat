@echo off
if not exist venv python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
python setup_db.py
pause
