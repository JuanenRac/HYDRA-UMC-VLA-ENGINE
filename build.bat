@echo off
REM =============================================================================
REM HYDRA-UMC-VLA-ENGINE - build.bat
REM Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
REM GPL-3.0 - see LICENSE
REM =============================================================================
REM Builds HYDRA-UMC-VLA-ENGINE: creates/activates a venv, installs the
REM project (editable) and verifies it compiles/imports cleanly. Run this
REM before run.bat.
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo  ===============================================================
echo   H Y D R A - U M C - V L A - E N G I N E  -  build
echo  ===============================================================
echo   Vision-Language-Action engine (Hailo-10)
echo   Author:  JuanenRac (Electro Hobby 3D)
echo   License: GPL-3.0 (see LICENSE.md)
echo  ===============================================================
echo.

echo [1/4] Bumping version number (odometer bump, see bump_version.py)...
python bump_version.py
if errorlevel 1 ( echo NATIVE VERSION BUMP FAILED. & pause & exit /b 1 )
python "%~dp0bump_manifest_version.py" --sync
if errorlevel 1 ( echo VERSION SYNCHRONIZATION FAILED. & pause & exit /b 1 )
if errorlevel 1 goto :error
echo       Done.
echo.

echo [2/4] Creating/activating virtual environment...
if not exist .venv (
    python -m venv .venv
    if errorlevel 1 goto :error
)
call .venv\Scripts\activate.bat
if errorlevel 1 goto :error
echo       Done.
echo.

echo [3/4] Installing project (editable) into the venv...
python -m pip install --upgrade pip >nul
if errorlevel 1 goto :error
python -m pip install -e .
if errorlevel 1 goto :error
echo       Done.
echo.

echo [4/4] Verifying the package compiles/imports without errors...
python -m py_compile src\hydra_umc_vla_engine\__init__.py src\hydra_umc_vla_engine\main.py
if errorlevel 1 goto :error
python -c "import hydra_umc_vla_engine; print('import OK - version', hydra_umc_vla_engine.__version__)"
if errorlevel 1 goto :error
echo       Done.
echo.

echo  ===============================================================
echo   Build complete. Run run.bat to execute the entry point.
echo  ===============================================================
echo.
exit /b 0

:error
echo.
echo   BUILD FAILED - see the output above.
exit /b 1
