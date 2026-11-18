#!/usr/bin/env bash
set -e
python3 -m pip install --upgrade -r requirements-dev.txt
python3 -m PyInstaller --onefile --windowed --clean --name AndromicLauncher main.py
echo "Done: dist/AndromicLauncher"
