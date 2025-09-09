@echo off
echo Starting Intibot...

REM Activate virtual environment
call venv\Scripts\activate

REM Run the bot (use cached settings)
python intibot.py

pause
