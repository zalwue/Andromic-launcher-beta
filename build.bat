@echo off
setlocal
py -m pip install --upgrade -r requirements-dev.txt
if errorlevel 1 exit /b %errorlevel%
py -m PyInstaller --noconfirm --onefile --noconsole --clean --name AndromicLauncher ^
  --icon=assets/icon.ico --add-data "assets;assets" ^
  --collect-submodules andromic --collect-all PySide6 main.py
if errorlevel 1 exit /b %errorlevel%
echo.
echo Done: dist\AndromicLauncher.exe
pause
