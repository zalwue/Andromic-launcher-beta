@echo off
py -m pip install --upgrade pyinstaller
py -m PyInstaller --onefile --noconsole --clean --name AndromicLauncher main.py
echo.
echo Done: dist\AndromicLauncher.exe
pause
