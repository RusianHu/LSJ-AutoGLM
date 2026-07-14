@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

rem Build the official Windows x64 directory distribution.
rem Keep this file ASCII-only so cmd.exe can parse it on legacy code pages.

cd /d "%~dp0\.."

set "APP_NAME=OpenAutoGLM-GUI"
set "ENTRY=gui_app.py"
set "BUILD_ROOT=%CD%\build\pyinstaller-gui-onedir"
set "PYI_DIST=%BUILD_ROOT%\dist"
set "WORK_DIR=%BUILD_ROOT%\work"
set "SPEC_DIR=%BUILD_ROOT%\spec"
set "RUNTIME_ROOT=%BUILD_ROOT%\runtime"
set "RELEASE_ROOT=%CD%\release"
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

if not exist "%CD%\VERSION" (
    echo [ERROR] VERSION was not found.
    exit /b 1
)
set /p "APP_VERSION="<"%CD%\VERSION"
if not defined APP_VERSION (
    echo [ERROR] VERSION is empty.
    exit /b 1
)

set "PACKAGE_BASENAME=%APP_NAME%-v%APP_VERSION%-windows-x64"
set "PYI_OUTPUT=%PYI_DIST%\%APP_NAME%"
set "STAGE_DIR=%RELEASE_ROOT%\%PACKAGE_BASENAME%"
set "ZIP_PATH=%RELEASE_ROOT%\%PACKAGE_BASENAME%.zip"
set "CHECKSUM_PATH=%ZIP_PATH%.sha256"

set "VENV_DIR=%OPEN_AUTOGLM_BUILD_VENV%"
if not defined VENV_DIR set "VENV_DIR=%CD%\venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo [INFO] Project root : %CD%
echo [INFO] Version      : %APP_VERSION%
echo [INFO] Python       : %VENV_PYTHON%
echo [INFO] Release ZIP  : %ZIP_PATH%

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Project venv was not found: %VENV_PYTHON%
    echo [ERROR] Create it and install requirements-build.txt first.
    exit /b 1
)
if not exist "%POWERSHELL%" (
    echo [ERROR] Windows PowerShell was not found: %POWERSHELL%
    exit /b 1
)

"%VENV_PYTHON%" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller is missing from the build venv.
    echo [ERROR] Run: "%VENV_PYTHON%" -m pip install -r requirements-build.txt
    exit /b 1
)

rem Resolve the Android Platform-Tools directory.
set "ADB_DIR=%OPEN_AUTOGLM_BUILD_ADB_DIR%"
set "ADB_EXE="
if not defined ADB_DIR if exist "%CD%\platform-tools\adb.exe" set "ADB_DIR=%CD%\platform-tools"
if not defined ADB_DIR (
    for /f "delims=" %%I in ('where adb 2^>nul') do if not defined ADB_EXE set "ADB_EXE=%%I"
    if defined ADB_EXE for %%I in ("!ADB_EXE!") do set "ADB_DIR=%%~dpI"
)
if not defined ADB_DIR (
    echo [ERROR] ADB runtime was not found. Set OPEN_AUTOGLM_BUILD_ADB_DIR.
    exit /b 1
)
for %%F in (adb.exe AdbWinApi.dll AdbWinUsbApi.dll libwinpthread-1.dll) do (
    if not exist "!ADB_DIR!\%%F" (
        echo [ERROR] Required ADB file is missing: !ADB_DIR!\%%F
        exit /b 1
    )
)

rem Resolve the scrcpy directory. Its bundled adb is intentionally not copied.
set "SCRCPY_DIR=%OPEN_AUTOGLM_BUILD_SCRCPY_DIR%"
set "SCRCPY_EXE="
if not defined SCRCPY_DIR if exist "%CD%\scrcpy\scrcpy.exe" set "SCRCPY_DIR=%CD%\scrcpy"
if not defined SCRCPY_DIR (
    for /f "delims=" %%I in ('where scrcpy 2^>nul') do if not defined SCRCPY_EXE set "SCRCPY_EXE=%%I"
    if defined SCRCPY_EXE for %%I in ("!SCRCPY_EXE!") do set "SCRCPY_DIR=%%~dpI"
)
if not defined SCRCPY_DIR (
    echo [ERROR] scrcpy runtime was not found. Set OPEN_AUTOGLM_BUILD_SCRCPY_DIR.
    exit /b 1
)
for %%F in (scrcpy.exe scrcpy-server SDL2.dll avcodec-61.dll avformat-61.dll avutil-59.dll swresample-5.dll libusb-1.0.dll) do (
    if not exist "!SCRCPY_DIR!\%%F" (
        echo [ERROR] Required scrcpy file is missing: !SCRCPY_DIR!\%%F
        exit /b 1
    )
)

set "ADB_KEYBOARD_APK=%OPEN_AUTOGLM_BUILD_ADBKEYBOARD_APK%"
if not defined ADB_KEYBOARD_APK set "ADB_KEYBOARD_APK=%CD%\ADBKeyboard.apk"
if not exist "%ADB_KEYBOARD_APK%" (
    echo [ERROR] ADBKeyboard.apk was not found: %ADB_KEYBOARD_APK%
    exit /b 1
)

rem Always build from clean, task-specific directories. Never reuse dist/.
if exist "%BUILD_ROOT%" rmdir /s /q "%BUILD_ROOT%"
if exist "%STAGE_DIR%" rmdir /s /q "%STAGE_DIR%"
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%"
if exist "%CHECKSUM_PATH%" del /f /q "%CHECKSUM_PATH%"
mkdir "%RUNTIME_ROOT%\platform-tools" || exit /b 1
mkdir "%RUNTIME_ROOT%\scrcpy" || exit /b 1
if not exist "%RELEASE_ROOT%" mkdir "%RELEASE_ROOT%" || exit /b 1

for %%F in (adb.exe AdbWinApi.dll AdbWinUsbApi.dll libwinpthread-1.dll) do copy /y "!ADB_DIR!\%%F" "%RUNTIME_ROOT%\platform-tools\%%F" >nul || exit /b 1
for %%F in (NOTICE.txt source.properties) do if exist "!ADB_DIR!\%%F" copy /y "!ADB_DIR!\%%F" "%RUNTIME_ROOT%\platform-tools\%%F" >nul || exit /b 1
for %%F in (scrcpy.exe scrcpy-server SDL2.dll avcodec-61.dll avformat-61.dll avutil-59.dll swresample-5.dll libusb-1.0.dll) do copy /y "!SCRCPY_DIR!\%%F" "%RUNTIME_ROOT%\scrcpy\%%F" >nul || exit /b 1
if exist "!SCRCPY_DIR!\icon.png" copy /y "!SCRCPY_DIR!\icon.png" "%RUNTIME_ROOT%\scrcpy\icon.png" >nul || exit /b 1

set "EXCLUDE_ARGS="
for %%M in (
    IPython pytest py jedi nbformat matplotlib matplotlib_inline mpl_toolkits
    numpy pandas scipy pyarrow torch torchvision torchaudio torchgen triton
    transformers tokenizers accelerate safetensors bitsandbytes tensorflow
    tensorboard keras onnxruntime cv2 imageio imageio_ffmpeg av decord pygame
    shapely lxml grpc google.cloud.storage black
) do set "EXCLUDE_ARGS=!EXCLUDE_ARGS! --exclude-module %%M"

echo [INFO] Building the onedir application...
"%VENV_PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name "%APP_NAME%" ^
  --distpath "%PYI_DIST%" ^
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
  --add-data "%CD%\gui\assets;gui\assets" ^
  --add-data "%RUNTIME_ROOT%\platform-tools;platform-tools" ^
  --add-data "%RUNTIME_ROOT%\scrcpy;scrcpy" ^
  --add-data "%ADB_KEYBOARD_APK%;." ^
  !EXCLUDE_ARGS! ^
  "%ENTRY%"
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)
if not exist "%PYI_OUTPUT%\%APP_NAME%.exe" (
    echo [ERROR] PyInstaller output is incomplete: %PYI_OUTPUT%
    exit /b 1
)

echo [INFO] Preparing the clean release directory...
robocopy "%PYI_OUTPUT%" "%STAGE_DIR%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo [ERROR] Failed to stage the PyInstaller output.
    exit /b 1
)

rem PyInstaller detects scrcpy DLLs as binaries and may duplicate them in _internal.
rem The copies beside scrcpy.exe are retained; the verified duplicate root copies are removed.
for %%F in (avcodec-61.dll avformat-61.dll avutil-59.dll libusb-1.0.dll SDL2.dll swresample-5.dll) do (
    if exist "%STAGE_DIR%\_internal\scrcpy\%%F" if exist "%STAGE_DIR%\_internal\%%F" del /f /q "%STAGE_DIR%\_internal\%%F"
)

copy /y "%CD%\.env.example" "%STAGE_DIR%\.env.example" >nul || exit /b 1
copy /y "%CD%\LICENSE" "%STAGE_DIR%\LICENSE" >nul || exit /b 1
copy /y "%CD%\README.md" "%STAGE_DIR%\README.md" >nul || exit /b 1

for /f "delims=" %%I in ('"%VENV_PYTHON%" --version 2^>^&1') do if not defined PYTHON_VERSION set "PYTHON_VERSION=%%I"
for /f "delims=" %%I in ('"%VENV_PYTHON%" -m PyInstaller --version 2^>^&1') do if not defined PYINSTALLER_VERSION set "PYINSTALLER_VERSION=%%I"
for /f "delims=" %%I in ('"%RUNTIME_ROOT%\platform-tools\adb.exe" version 2^>^&1') do if not defined ADB_VERSION set "ADB_VERSION=%%I"
for /f "delims=" %%I in ('"%RUNTIME_ROOT%\scrcpy\scrcpy.exe" --version 2^>^&1') do if not defined SCRCPY_VERSION set "SCRCPY_VERSION=%%I"
>"%STAGE_DIR%\BUILD-INFO.txt" (
    echo Application: %APP_NAME% %APP_VERSION%
    echo Target: Windows x64 onedir
    echo Python: !PYTHON_VERSION!
    echo PyInstaller: !PYINSTALLER_VERSION!
    echo ADB: !ADB_VERSION!
    echo scrcpy: !SCRCPY_VERSION!
)

rem Reject local state and secrets before any archive is created.
if exist "%STAGE_DIR%\.env" (
    echo [ERROR] Refusing to package .env.
    exit /b 1
)
if exist "%STAGE_DIR%\gui_history" (
    echo [ERROR] Refusing to package gui_history.
    exit /b 1
)
for /r "%STAGE_DIR%" %%F in (*.log .open-autoglm-launcher.json) do if exist "%%F" (
    echo [ERROR] Refusing to package local state: %%F
    exit /b 1
)

for %%F in (
    "%STAGE_DIR%\%APP_NAME%.exe"
    "%STAGE_DIR%\.env.example"
    "%STAGE_DIR%\LICENSE"
    "%STAGE_DIR%\_internal\ADBKeyboard.apk"
    "%STAGE_DIR%\_internal\platform-tools\adb.exe"
    "%STAGE_DIR%\_internal\scrcpy\scrcpy.exe"
) do if not exist "%%~F" (
    echo [ERROR] Required release file is missing: %%~F
    exit /b 1
)

echo [INFO] Running packaged smoke tests...
set "PATH=%STAGE_DIR%\_internal\platform-tools;%STAGE_DIR%\_internal\scrcpy;%SystemRoot%\System32;%SystemRoot%"
"%STAGE_DIR%\%APP_NAME%.exe" --gui-task-runner --list-apps >"%BUILD_ROOT%\runner-smoke.stdout.txt" 2>"%BUILD_ROOT%\runner-smoke.stderr.txt"
if errorlevel 1 (
    echo [ERROR] Packaged task runner smoke test failed.
    type "%BUILD_ROOT%\runner-smoke.stderr.txt"
    exit /b 1
)
"%STAGE_DIR%\_internal\platform-tools\adb.exe" version >nul 2>nul || exit /b 1
"%STAGE_DIR%\_internal\scrcpy\scrcpy.exe" --version >nul 2>nul || exit /b 1

echo [INFO] Creating release archive and checksum...
"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -LiteralPath '%STAGE_DIR%' -DestinationPath '%ZIP_PATH%' -CompressionLevel Optimal"
if errorlevel 1 exit /b 1
"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $s=[IO.File]::OpenRead('%ZIP_PATH%'); try { $sha=[Security.Cryptography.SHA256]::Create(); $h=([BitConverter]::ToString($sha.ComputeHash($s))).Replace('-','').ToLowerInvariant() } finally { $s.Dispose() }; [IO.File]::WriteAllText('%CHECKSUM_PATH%', $h + '  ' + [IO.Path]::GetFileName('%ZIP_PATH%') + [Environment]::NewLine, [Text.Encoding]::ASCII)"
if errorlevel 1 exit /b 1
if not exist "%CHECKSUM_PATH%" (
    echo [ERROR] Checksum file was not created: %CHECKSUM_PATH%
    exit /b 1
)

"%VENV_PYTHON%" -c "from pathlib import Path; d=Path(r'%STAGE_DIR%'); z=Path(r'%ZIP_PATH%'); total=sum(p.stat().st_size for p in d.rglob('*') if p.is_file()); print(f'[INFO] Release directory: {d}'); print(f'[INFO] Raw size: {total / 1024 / 1024:.2f} MiB'); print(f'[INFO] ZIP: {z}'); print(f'[INFO] ZIP size: {z.stat().st_size / 1024 / 1024:.2f} MiB')"
if errorlevel 1 exit /b 1

echo [INFO] Official onedir build completed successfully.
endlocal
exit /b 0
