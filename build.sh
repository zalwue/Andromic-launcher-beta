#!/usr/bin/env bash
set -euo pipefail

PYTHON="${PYTHON:-python3}"

# Keep any native extensions compiled from source compatible with baseline
# x86-64 CPUs (including older Intel chips without AVX/AVX2). This does not
# rewrite prebuilt wheels; those must be audited separately. Never use -march=native
# for distributable Linux builds.
if [[ "$(uname -s)" == "Linux" ]]; then
    if [[ "$(uname -m)" == "x86_64" ]]; then
        export CFLAGS="-march=x86-64 -mtune=generic"
        export CXXFLAGS="-march=x86-64 -mtune=generic"
    fi
    if command -v getconf >/dev/null 2>&1; then
        glibc_version="$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}')"
        if [[ -n "$glibc_version" ]] && [[ "$(printf '2.35\n%s\n' "$glibc_version" | sort -V | tail -n1)" != "2.35" ]]; then
            echo "Warning: building on glibc $glibc_version. For older Linux compatibility, build on Ubuntu 22.04 (glibc 2.35) or older."
        fi
    fi
fi

"$PYTHON" -m pip install --upgrade -r requirements-dev.txt

args=(--noconfirm --onefile --windowed --clean --name AndromicLauncher
      --collect-submodules andromic --collect-all PySide6
      --add-data "assets:assets")
if [[ "$(uname -s)" == "Darwin" ]]; then
    args+=(--icon=assets/icon.png --osx-bundle-identifier com.andromic.launcher)
fi
"$PYTHON" -m PyInstaller "${args[@]}" main.py
echo "Done: dist/AndromicLauncher"
