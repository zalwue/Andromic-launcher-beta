@echo off
py -m pip install --upgrade -r requirements-dev.txt
py -m PyInstaller --onefile --noconsole --clean --name AndromicLauncher main.py
echo.
echo Done: dist\AndromicLauncher.exe
pause
