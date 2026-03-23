@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0\.."

set "PYTHON=python"
set "ENTRY=gui_app.py"
set "APP_NAME=OpenAutoGLM-GUI"
set "DIST_DIR=dist"
set "WORK_DIR=build\pyinstaller-gui"
set "SPEC_DIR=build\spec"
set "OUTPUT_EXE=%DIST_DIR%\%APP_NAME%.exe"
set "PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

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

echo [INFO] Project root: %CD%
echo [INFO] Output exe : %OUTPUT_EXE%

where %PYTHON% >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python was not found in PATH.
    exit /b 1
)

%PYTHON% -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [WARN] PyInstaller is missing. Installing from Aliyun mirror...
    %PYTHON% -m pip install --upgrade pyinstaller -i %PIP_INDEX_URL%
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        exit /b 1
    )
)

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%WORK_DIR%" mkdir "%WORK_DIR%"
if not exist "%SPEC_DIR%" mkdir "%SPEC_DIR%"

if exist "%OUTPUT_EXE%" del /f /q "%OUTPUT_EXE%" >nul 2>nul

echo [INFO] Starting PyInstaller one-file build...
if defined EXCLUDE_ARGS echo [INFO] Excluding heavy modules:%EXCLUDE_ARGS%
%PYTHON% -m PyInstaller ^
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

for %%I in ("%OUTPUT_EXE%") do set "OUTPUT_BYTES=%%~zI"
%PYTHON% -c "from pathlib import Path; p = Path(r'%OUTPUT_EXE%').resolve(); size = p.stat().st_size / (1024 * 1024); print(f'[INFO] Built exe: {p}'); print(f'[INFO] File size: {size:.2f} MiB')"

echo [INFO] Build completed successfully.
endlocal
exit /b 0
