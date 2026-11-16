@echo off
rem Fetch new Fox games, analyse them and publish the site. Safe to run on a schedule:
rem with no new games it ends in a few seconds without starting KataGo or touching git.
rem Output is appended to logs\update.log.
cd /d "%~dp0.."
if not exist logs mkdir logs
python -m pipeline analyze --latest --publish >> logs\update.log 2>&1
exit /b %errorlevel%
