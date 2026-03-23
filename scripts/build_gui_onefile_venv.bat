@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

rem ============================================================
rem  build_gui_venv.bat
rem  Build GUI one-file EXE with the project venv.
rem  Keep this batch file ASCII-only. Non-ASCII text may be
rem  misparsed by cmd.exe when launched from Explorer or a
rem  legacy code-page environment.
rem ============================================================

cd /d "%~dp0\.."

set "VENV_PYTHON=venv\Scripts\python.exe"
set "VENV_PIP=venv\Scripts\pip.exe"
set "ENTRY=gui_app.py"
set "APP_NAME=OpenAutoGLM-GUI"
set "DIST_DIR=dist"
set "WORK_DIR=build\pyinstaller-gui"
set "SPEC_DIR=build\spec"
set "OUTPUT_EXE=%DIST_DIR%\%APP_NAME%.exe"
set "PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/"
set "ADB_KEYBOARD_APK=ADBKeyboard.apk"
set "EXTRA_DATA_ARGS="
set "ADB_EXE="
set "ADB_DIR="
set "SCRCPY_EXE="
set "SCRCPY_DIR="

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo [INFO] Project root : %CD%
echo [INFO] Using venv   : %VENV_PYTHON%
echo [INFO] Output EXE   : %OUTPUT_EXE%

rem ---- Check venv ----
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Project venv was not found. Run: python -m venv venv
    exit /b 1
)

rem ---- Check / install PyInstaller ----
"%VENV_PYTHON%" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [WARN] PyInstaller is missing. Installing from Aliyun mirror...
    "%VENV_PIP%" install pyinstaller -i %PIP_INDEX_URL% --trusted-host mirrors.aliyun.com
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        exit /b 1
    )
)

rem ---- Prepare directories ----
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%WORK_DIR%" mkdir "%WORK_DIR%"
if not exist "%SPEC_DIR%" mkdir "%SPEC_DIR%"
if exist "%OUTPUT_EXE%" del /f /q "%OUTPUT_EXE%" >nul 2>nul

rem ---- Exclude heavy unrelated modules ----
set "EXCLUDE_ARGS="
for %%M in (
    IPython
    pytest
    py
    jedi
    nbformat
    matplotlib
    matplotlib_inline
    mpl_toolkits
    numpy
    pandas
    scipy
    pyarrow
    torch
    torchvision
    torchaudio
    torchgen
    triton
    transformers
    tokenizers
    accelerate
    safetensors
    bitsandbytes
    tensorflow
    tensorboard
    keras
    onnxruntime
    cv2
    imageio
    imageio_ffmpeg
    av
    decord
    pygame
    shapely
    lxml
    grpc
    google.cloud.storage
    black
) do (
    set "EXCLUDE_ARGS=!EXCLUDE_ARGS! --exclude-module %%M"
)

rem ---- Collect portable runtime dependencies ----
if exist "%CD%\platform-tools\adb.exe" set "ADB_DIR=%CD%\platform-tools"
if not defined ADB_DIR (
    for /f "delims=" %%I in ('where adb 2^>nul') do (
        if not defined ADB_EXE set "ADB_EXE=%%I"
    )
    if defined ADB_EXE for %%I in ("%ADB_EXE%") do set "ADB_DIR=%%~dpI"
)
if defined ADB_DIR (
    echo [INFO] Bundling ADB runtime from: %ADB_DIR%
    set "EXTRA_DATA_ARGS=!EXTRA_DATA_ARGS! --add-data ""%ADB_DIR%;platform-tools"""
) else (
    echo [WARN] ADB runtime was not found. The packaged app will rely on an external adb.
)

if exist "%CD%\scrcpy\scrcpy.exe" set "SCRCPY_DIR=%CD%\scrcpy"
if not defined SCRCPY_DIR (
    for /f "delims=" %%I in ('where scrcpy 2^>nul') do (
        if not defined SCRCPY_EXE set "SCRCPY_EXE=%%I"
    )
    if defined SCRCPY_EXE for %%I in ("%SCRCPY_EXE%") do set "SCRCPY_DIR=%%~dpI"
)
if defined SCRCPY_DIR (
    echo [INFO] Bundling scrcpy runtime from: %SCRCPY_DIR%
    set "EXTRA_DATA_ARGS=!EXTRA_DATA_ARGS! --add-data ""%SCRCPY_DIR%;scrcpy"""
) else (
    echo [WARN] scrcpy runtime was not found. The packaged app will fall back to ADB screenshots.
)

if exist "%CD%\%ADB_KEYBOARD_APK%" (
    echo [INFO] Bundling ADB Keyboard APK: %ADB_KEYBOARD_APK%
    set "EXTRA_DATA_ARGS=!EXTRA_DATA_ARGS! --add-data ""%CD%\%ADB_KEYBOARD_APK%;."""
) else (
    echo [WARN] ADBKeyboard.apk was not found in the project root.
)

echo [INFO] Starting PyInstaller one-file build using the project venv...
if defined EXCLUDE_ARGS echo [INFO] Excluding heavy modules:%EXCLUDE_ARGS%
if defined EXTRA_DATA_ARGS echo [INFO] Including portable runtime assets:%EXTRA_DATA_ARGS%

"%VENV_PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "%APP_NAME%" ^
  --distpath "%DIST_DIR%" ^
  --workpath "%WORK_DIR%" ^
  --specpath "%SPEC_DIR%" ^
  --paths "%CD%" ^
  --hidden-import gui.i18n.locales.cn ^
  --hidden-import gui.i18n.locales.en ^
  --hidden-import qrcode ^
  --hidden-import qrcode.image.pil ^
  --hidden-import openai ^
  --collect-submodules gui.i18n.locales ^
  --collect-submodules phone_agent.config ^
  --collect-submodules openai ^
  --copy-metadata openai ^
  %EXTRA_DATA_ARGS% ^
  %EXCLUDE_ARGS% ^
  "%ENTRY%"

if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)

if not exist "%OUTPUT_EXE%" (
    echo [ERROR] Build finished but output was not found.
    exit /b 1
)

"%VENV_PYTHON%" -c "from pathlib import Path; p=Path(r'%OUTPUT_EXE%').resolve(); size=p.stat().st_size/(1024*1024); print(f'[INFO] Built exe: {p}'); print(f'[INFO] File size: {size:.2f} MiB')"

echo [INFO] Build completed successfully.
endlocal
exit /b 0
