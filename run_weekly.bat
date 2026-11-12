@echo off
rem Weekly run of the flyer pipeline - Windows Task Scheduler starts this file every week.
rem It runs "python run.py" with the project's own Python and writes everything into logs\last_run.txt

rem 1. go to the project folder (the folder this file is in)
cd /d "%~dp0"

rem 2. let Python write German letters (u-umlaut, sz, guillemets) into the log without errors
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

rem 3. run the pipeline and write everything into the log (only the last run is kept)
if not exist logs mkdir logs
echo Weekly run started: %date% %time% > logs\last_run.txt
".venv\Scripts\python.exe" run.py >> logs\last_run.txt 2>&1
set RESULT=%errorlevel%
echo Weekly run finished: %date% %time% - result %RESULT% (0 = OK) >> logs\last_run.txt

rem 4. tell Task Scheduler whether it worked (0 = OK)
exit /b %RESULT%