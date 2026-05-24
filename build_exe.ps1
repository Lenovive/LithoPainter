# Build the Lithopainter Windows installer end-to-end.
# Run from the project root in PowerShell:
#     .\build_exe.ps1
#
# Prereqs on the build machine (one-time):
#   - The project venv (.\.venv) created by Lithopainter.bat
#   - Inno Setup 6+ installed and `iscc.exe` on PATH (or edit $InnoSetup below)
#
# Steps:
#   1. Install/refresh PyInstaller in the venv.
#   2. Run PyInstaller against build\lithopainter.spec → dist\Lithopainter\.
#   3. Download Adoptium Temurin JRE 21 (Windows x64) and stage as
#      dist\Lithopainter\jre\.
#   4. Compile the Inno Setup script → installer-out\LithopainterSetup.exe.

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'   # faster Invoke-WebRequest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$VenvPy   = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$SpecFile = Join-Path $RepoRoot 'build\lithopainter.spec'
$IssFile  = Join-Path $RepoRoot 'build\installer.iss'
$DistRoot = Join-Path $RepoRoot 'dist\Lithopainter'
$WorkDir  = Join-Path $RepoRoot 'build\work'
$JreZip   = Join-Path $RepoRoot 'build\jre.zip'
$JreTemp  = Join-Path $RepoRoot 'build\jre-extract'
$JreDest  = Join-Path $DistRoot 'jre'

if (-not (Test-Path $VenvPy)) {
    throw "Project venv not found at $VenvPy. Run Lithopainter.bat once first to create it."
}

# 1. PyInstaller --------------------------------------------------------------
Write-Host '[build_exe] Installing/upgrading PyInstaller in venv...' -ForegroundColor Cyan
& $VenvPy -m pip install --quiet --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'pip install pyinstaller failed' }

Write-Host '[build_exe] Cleaning previous build/dist...' -ForegroundColor Cyan
foreach ($p in @($WorkDir, (Join-Path $RepoRoot 'dist'))) {
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}

Write-Host '[build_exe] Running PyInstaller...' -ForegroundColor Cyan
& $VenvPy -m PyInstaller --noconfirm --clean `
    --workpath $WorkDir `
    --distpath (Join-Path $RepoRoot 'dist') `
    $SpecFile
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
if (-not (Test-Path (Join-Path $DistRoot 'Lithopainter.exe'))) {
    throw "Expected Lithopainter.exe under $DistRoot"
}

# 2. Adoptium Temurin JRE -----------------------------------------------------
Write-Host '[build_exe] Downloading Adoptium Temurin JRE 21 (windows x64)...' -ForegroundColor Cyan
$JreUrl = 'https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jre/hotspot/normal/eclipse'
if (Test-Path $JreZip)  { Remove-Item -Force $JreZip }
if (Test-Path $JreTemp) { Remove-Item -Recurse -Force $JreTemp }
Invoke-WebRequest -Uri $JreUrl -OutFile $JreZip

Write-Host '[build_exe] Extracting JRE...' -ForegroundColor Cyan
Expand-Archive -Path $JreZip -DestinationPath $JreTemp -Force
$JreSrc = (Get-ChildItem -Path $JreTemp -Directory | Select-Object -First 1).FullName
if (-not $JreSrc) { throw 'Could not locate extracted JRE root.' }

Write-Host "[build_exe] Staging JRE into $JreDest..." -ForegroundColor Cyan
if (Test-Path $JreDest) { Remove-Item -Recurse -Force $JreDest }
Copy-Item -Recurse $JreSrc $JreDest
if (-not (Test-Path (Join-Path $JreDest 'bin\java.exe'))) {
    throw "Bundled JRE missing bin\java.exe under $JreDest"
}

# 3. Inno Setup ---------------------------------------------------------------
$InnoSetup = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $InnoSetup) {
    foreach ($candidate in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path $candidate) { $InnoSetup = $candidate; break }
    }
}
if (-not $InnoSetup) {
    throw 'Inno Setup compiler (iscc.exe) not found. Install Inno Setup 6 from https://jrsoftware.org/isdl.php'
}

Write-Host "[build_exe] Compiling installer via $InnoSetup..." -ForegroundColor Cyan
& $InnoSetup $IssFile
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed' }

$InstallerPath = Join-Path $RepoRoot 'installer-out\LithopainterSetup.exe'
if (Test-Path $InstallerPath) {
    $sizeMb = [math]::Round((Get-Item $InstallerPath).Length / 1MB, 1)
    Write-Host "`n[build_exe] Done: $InstallerPath ($sizeMb MB)" -ForegroundColor Green
} else {
    throw "Installer not produced at $InstallerPath"
}
