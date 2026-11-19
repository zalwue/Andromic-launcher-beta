#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade -r requirements-dev.txt

args=(--onefile --windowed --clean --name AndromicLauncher --add-data "assets:assets")
if [[ "$(uname -s)" == "Darwin" ]]; then
    args+=(--icon=assets/icon.png)
fi
python3 -m PyInstaller "${args[@]}" main.py
echo "Done: dist/AndromicLauncher"
