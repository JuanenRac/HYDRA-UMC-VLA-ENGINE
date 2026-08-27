#!/usr/bin/env bash
# =============================================================================
# HYDRA-UMC-VLA-ENGINE - build.sh
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
# Builds HYDRA-UMC-VLA-ENGINE: creates/activates a venv, installs the
# project (editable) and verifies it compiles/imports cleanly. Run this
# before run.sh.
#
# Usage:
#   chmod +x build.sh   (one-time)
#   ./build.sh
set -euo pipefail
cd "$(dirname "$0")"

echo
echo " ==============================================================="
echo "  H Y D R A - U M C - V L A - E N G I N E  -  build"
echo " ==============================================================="
echo "  Vision-Language-Action engine (Hailo-10)"
echo "  Author:  JuanenRac (Electro Hobby 3D)"
echo "  License: GPL-3.0 (see LICENSE.md)"
echo " ==============================================================="
echo

echo "[1/4] Bumping version number (odometer bump, see bump_version.py)..."
python3 bump_version.py || exit 1
python3 "$(dirname "$0")/bump_manifest_version.py" --sync || exit 1
echo "      Done."
echo

echo "[2/4] Creating/activating virtual environment..."
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
# venv layout differs by OS: bin/activate on Linux/macOS, Scripts/activate
# on Windows (also true for a Windows Python venv used from Git Bash).
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
elif [ -f .venv/Scripts/activate ]; then
    source .venv/Scripts/activate
else
    echo "ERROR: could not find the venv activate script." >&2
    exit 1
fi
echo "      Done."
echo

echo "[3/4] Installing project (editable) into the venv..."
python -m pip install --upgrade pip >/dev/null
python -m pip install -e .
echo "      Done."
echo

echo "[4/4] Verifying the package compiles/imports without errors..."
python -m py_compile src/hydra_umc_vla_engine/__init__.py src/hydra_umc_vla_engine/main.py
python -c "import hydra_umc_vla_engine; print('import OK - version', hydra_umc_vla_engine.__version__)"
echo "      Done."
echo

echo " ==============================================================="
echo "  Build complete. Run ./run.sh to execute the entry point."
echo " ==============================================================="
echo
