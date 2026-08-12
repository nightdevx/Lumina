<#
    One command, one installer.

        .\build.ps1              # tests + exe + installer
        .\build.ps1 -SkipTests   # exe + installer only
        .\build.ps1 -ExeOnly     # stop after PyInstaller

    Output: build\output\LuminaSetup-<version>.exe
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$ExeOnly
)

# Not "Stop": PyInstaller and pip write progress to stderr, and Windows
# PowerShell turns any native-command stderr line into a terminating
# NativeCommandError. Every native call below checks $LASTEXITCODE instead.
$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$Output = Join-Path $Root "build\output"

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

# ---- 1. environment -------------------------------------------------------
Step "Python ortami"
if (-not (Test-Path $Python)) {
    Write-Host "   .venv yok, olusturuluyor..."
    & py -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "venv olusturulamadi" }
}
Write-Host "   $Python"
& $Python -m pip install --quiet --upgrade pip
& $Python -m pip install --quiet -r (Join-Path $Root "requirements-dev.txt")
if ($LASTEXITCODE -ne 0) { throw "bagimliliklar kurulamadi" }
& $Python -c "import PySide6, win32com.client, PyInstaller"
if ($LASTEXITCODE -ne 0) { throw "bagimlilik dogrulamasi basarisiz" }

# ---- 2. tests -------------------------------------------------------------
if (-not $SkipTests) {
    Step "Testler"
    & $Python -m pytest (Join-Path $Root "tests") -q
    if ($LASTEXITCODE -ne 0) { throw "testler basarisiz - build durduruldu" }
}

# ---- 3. PyInstaller -------------------------------------------------------
Step "PyInstaller (onedir)"
if (Test-Path $Output) { Remove-Item $Output -Recurse -Force -ErrorAction Stop }
& $Python -m PyInstaller (Join-Path $Root "build\lumina.spec") `
    --clean --noconfirm `
    --distpath (Join-Path $Output "dist") `
    --workpath (Join-Path $Output "work")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller basarisiz" }

$ExePath = Join-Path $Output "dist\LUMINA\LUMINA.exe"
if (-not (Test-Path $ExePath)) { throw "LUMINA.exe uretilemedi" }
$DistSize = (Get-ChildItem (Join-Path $Output "dist\LUMINA") -Recurse -File |
             Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ("   dist klasoru: {0:N1} MB" -f $DistSize)

if ($ExeOnly) {
    Write-Host "`nBitti (installer atlandi): $ExePath" -ForegroundColor Green
    exit 0
}

# ---- 4. Inno Setup --------------------------------------------------------
Step "Inno Setup"
function Find-Iscc {
    # A non-admin `winget install` lands under %LOCALAPPDATA%\Programs, so that
    # path is checked first - the Program Files locations only exist after an
    # elevated or classic installer run.
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    $hit = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($hit) { return $hit }
    $onPath = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if ($onPath) { return $onPath }
    return $null
}

$Iscc = Find-Iscc
if (-not $Iscc) {
    Write-Host "   Inno Setup bulunamadi, winget ile kuruluyor..."
    & winget install --id JRSoftware.InnoSetup --silent --accept-package-agreements --accept-source-agreements
    $Iscc = Find-Iscc
}
if (-not $Iscc) { throw "Inno Setup kurulamadi. https://jrsoftware.org/isdl.php adresinden elle kurun." }

& $Iscc (Join-Path $Root "build\installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup derlemesi basarisiz" }

$Setup = Get-ChildItem (Join-Path $Output "LuminaSetup-*.exe") | Select-Object -First 1
Write-Host ("`nBitti: {0} ({1:N1} MB)" -f $Setup.FullName, ($Setup.Length / 1MB)) -ForegroundColor Green
