param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath,
    [switch]$ProbeDevice
)

$ErrorActionPreference = "Stop"
$archive = (Resolve-Path -LiteralPath $ArchivePath).Path
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$auditRoot = Join-Path $projectRoot "build\release-verification"
$extractRoot = Join-Path $auditRoot (Get-Date -Format "yyyyMMdd-HHmmss")
New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null

$checksumPath = "$archive.sha256"
if (Test-Path -LiteralPath $checksumPath) {
    $expected = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split "\s+")[0]
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    if ($actual -ne $expected) {
        throw "SHA-256 mismatch: expected $expected, got $actual"
    }
}

Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot
$exe = Get-ChildItem -LiteralPath $extractRoot -Filter "OpenAutoGLM-GUI.exe" -File -Recurse | Select-Object -First 1
if (-not $exe) {
    throw "OpenAutoGLM-GUI.exe was not found after extraction"
}
$packageRoot = $exe.Directory.FullName
$envPath = Join-Path $packageRoot ".env"
$envExamplePath = Join-Path $packageRoot ".env.example"
$licensePath = Join-Path $packageRoot "LICENSE"
$adbPath = Join-Path $packageRoot "_internal\platform-tools\adb.exe"
$scrcpyPath = Join-Path $packageRoot "_internal\scrcpy\scrcpy.exe"

foreach ($required in @($envExamplePath, $licensePath, $adbPath, $scrcpyPath)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required release file is missing: $required"
    }
}
if (Test-Path -LiteralPath $envPath) {
    throw "Release archive must not contain .env"
}

Get-ChildItem Env: | Where-Object Name -Like "OPEN_AUTOGLM_*" | ForEach-Object {
    Remove-Item -LiteralPath ("Env:" + $_.Name)
}
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"

$gui = $null
try {
    $gui = Start-Process -FilePath $exe.FullName -WorkingDirectory $packageRoot -PassThru
    Start-Sleep -Seconds 10
    $gui.Refresh()
    if ($gui.HasExited) {
        throw "GUI exited during the startup smoke test with code $($gui.ExitCode)"
    }
    $windowTitle = (Get-Process -Id $gui.Id).MainWindowTitle
    if (-not $windowTitle) {
        throw "GUI process is alive but no main window was detected"
    }
    if (-not (Test-Path -LiteralPath $envPath)) {
        throw "GUI did not create the default .env on first launch"
    }
    $nonEmptySensitive = @(
        Get-Content -LiteralPath $envPath |
            Where-Object { $_ -match '^\s*[^#=]*(API_KEY|SECRET|TOKEN|PASSWORD)[^=]*=\s*[^\s]+' }
    )
    if ($nonEmptySensitive.Count -ne 0) {
        throw "Generated .env contains non-empty sensitive values"
    }
}
finally {
    if ($gui -and -not $gui.HasExited) {
        Stop-Process -Id $gui.Id -Force -ErrorAction SilentlyContinue
    }
}

$stdoutPath = Join-Path $extractRoot "runner.stdout.txt"
$stderrPath = Join-Path $extractRoot "runner.stderr.txt"
$runner = Start-Process -FilePath $exe.FullName `
    -ArgumentList @("--gui-task-runner", "--list-devices") `
    -WorkingDirectory $packageRoot `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -Wait -PassThru
if ($runner.ExitCode -ne 0) {
    throw "Packaged task runner failed with code $($runner.ExitCode): $(Get-Content $stderrPath -Raw)"
}

& $adbPath version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Bundled adb failed with code $LASTEXITCODE"
}
& $scrcpyPath --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Bundled scrcpy failed with code $LASTEXITCODE"
}

if ($ProbeDevice) {
    $env:PATH = "$(Split-Path $adbPath);$env:SystemRoot\System32;$env:SystemRoot"
    & $scrcpyPath --list-displays
    if ($LASTEXITCODE -ne 0) {
        throw "scrcpy device probe failed with code $LASTEXITCODE"
    }
}

$archiveSize = (Get-Item -LiteralPath $archive).Length / 1MB
$rawSize = (Get-ChildItem -LiteralPath $packageRoot -File -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Output "Release verification passed"
Write-Output ("Archive: {0}" -f $archive)
Write-Output ("Raw size: {0:N2} MiB" -f $rawSize)
Write-Output ("ZIP size: {0:N2} MiB" -f $archiveSize)
Write-Output ("GUI title: {0}" -f $windowTitle)
Write-Output ("Generated .env sensitive values: 0")
Write-Output ("Task runner exit code: {0}" -f $runner.ExitCode)
