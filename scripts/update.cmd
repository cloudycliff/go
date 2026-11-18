@echo off
rem Fetch new Fox games, analyse them and publish the site. Safe to run on a schedule:
rem with no new games it ends in a few seconds without starting KataGo or touching git.
rem Output is appended to logs\update.log. Registered as a daily task by scripts\schedule.ps1.
cd /d "%~dp0.."
if not exist logs mkdir logs
echo ==== %date% %time% >> logs\update.log
rem Up to 10 new games a run (a busy weekend); the rest wait for the next run.
python -m pipeline analyze --latest --publish --max 10 >> logs\update.log 2>&1
exit /b %errorlevel%
