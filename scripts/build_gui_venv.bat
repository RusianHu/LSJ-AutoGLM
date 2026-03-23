@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

rem ============================================================
rem  build_gui_venv.bat
rem  使用项目内 ./venv 便携虚拟环境打包 GUI 为单文件 EXE
rem  用法：双击或在项目根目录执行 scripts\build_gui_venv.bat
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

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo [INFO] Project root : %CD%
echo [INFO] Using venv   : %VENV_PYTHON%
echo [INFO] Output EXE   : %OUTPUT_EXE%

rem ---- 检查 venv ----
if not exist "%VENV_PYTHON%" (
    echo [ERROR] 未找到 ./venv，请先执行: python -m venv venv
    exit /b 1
)

rem ---- 检查 / 安装 PyInstaller ----
"%VENV_PYTHON%" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [WARN] PyInstaller 未安装，正在从阿里云镜像安装...
    "%VENV_PIP%" install pyinstaller -i %PIP_INDEX_URL% --trusted-host mirrors.aliyun.com
    if errorlevel 1 (
        echo [ERROR] PyInstaller 安装失败
        exit /b 1
    )
)

rem ---- 准备目录 ----
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%WORK_DIR%" mkdir "%WORK_DIR%"
if not exist "%SPEC_DIR%" mkdir "%SPEC_DIR%"
if exist "%OUTPUT_EXE%" del /f /q "%OUTPUT_EXE%" >nul 2>nul

rem ---- 排除大型无关模块 ----
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

echo [INFO] 开始 PyInstaller 单文件打包（venv 环境）...

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
  --collect-submodules gui.i18n.locales ^
  --collect-submodules phone_agent.config ^
  %EXCLUDE_ARGS% ^
  "%ENTRY%"

if errorlevel 1 (
    echo [ERROR] PyInstaller 打包失败
    exit /b 1
)

if not exist "%OUTPUT_EXE%" (
    echo [ERROR] 打包完成但未找到输出文件
    exit /b 1
)

"%VENV_PYTHON%" -c "from pathlib import Path; p=Path(r'%OUTPUT_EXE%').resolve(); s=p.stat().st_size/1048576; print(f'[INFO] 已生成: {p}'); print(f'[INFO] 文件大小: {s:.2f} MiB')"

echo [INFO] 打包成功完成。
endlocal
exit /b 0
