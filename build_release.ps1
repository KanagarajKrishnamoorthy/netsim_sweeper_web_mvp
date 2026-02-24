param(
  [string]$Version = "",
  [switch]$SkipInstaller,
  [switch]$NoClean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Ensure-Command {
  param([string]$Name)
  $cmd = Get-Command $Name -ErrorAction SilentlyContinue
  if (-not $cmd) {
    throw "Required command not found in PATH: $Name"
  }
  return $cmd
}

function Stop-ListenerPort {
  param([int]$Port)
  $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
  if (-not $listeners) {
    return
  }
  $pids = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($procId in $pids) {
    try {
      Stop-Process -Id $procId -Force -ErrorAction Stop
      Write-Host "Stopped process $procId on port $Port"
    } catch {
      Write-Warning "Failed to stop process $procId on port ${Port}: $($_.Exception.Message)"
    }
  }
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $projectRoot "frontend"
$backendDir = Join-Path $projectRoot "backend"
$packagingDir = Join-Path $projectRoot "packaging"
$releaseDir = Join-Path $projectRoot "release"
$buildDir = Join-Path $releaseDir "_build"
$portableDir = Join-Path $releaseDir "portable\NetSimSweeper"
$installerOutDir = Join-Path $releaseDir "installer"
$venvDir = Join-Path $backendDir ".venv_release"
$venv313Python = Join-Path $backendDir ".venv313\Scripts\python.exe"
$venvPython = ""

if ([string]::IsNullOrWhiteSpace($Version)) {
  $packageJsonPath = Join-Path $frontendDir "package.json"
  $pkg = Get-Content $packageJsonPath -Raw | ConvertFrom-Json
  $Version = [string]$pkg.version
}

if (-not $NoClean) {
  Write-Step "Cleaning previous release artifacts"
  if (Test-Path $releaseDir) {
    Remove-Item $releaseDir -Recurse -Force
  }
}

New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
New-Item -ItemType Directory -Path $portableDir -Force | Out-Null
New-Item -ItemType Directory -Path $installerOutDir -Force | Out-Null

Write-Step "Verifying build dependencies"
Ensure-Command "python" | Out-Null
Ensure-Command "cmd" | Out-Null
Ensure-Command "npm" | Out-Null

Write-Step "Building frontend static assets"
Stop-ListenerPort -Port 5175
Push-Location $frontendDir
try {
  & cmd /c npm ci
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "npm ci failed. Falling back to npm install."
    & cmd /c npm install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
  }
  & cmd /c npm run build
  if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally {
  Pop-Location
}

Write-Step "Preparing Python build environment"
if (Test-Path $venv313Python) {
  $venvPython = $venv313Python
  Write-Host "Using existing backend virtual environment: $venvPython"
} else {
  $venvPython = Join-Path $venvDir "Scripts\python.exe"
  if (-not (Test-Path $venvPython)) {
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to create virtual environment at $venvDir"
    }
  }
}
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip in $venvPython" }
& $venvPython -m pip install -r (Join-Path $backendDir "requirements.txt")
if ($LASTEXITCODE -ne 0) {
  throw "Failed to install backend requirements. Use Python 3.11-3.13 or provide a prepared .venv313."
}
& $venvPython -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Failed to install pyinstaller in $venvPython" }

$frontendDist = Join-Path $frontendDir "dist"
if (-not (Test-Path (Join-Path $frontendDist "index.html"))) {
  throw "Frontend dist missing index.html at $frontendDist"
}

Write-Step "Building backend executable (PyInstaller onedir)"
$backendDistPath = Join-Path $buildDir "backend_dist"
$backendWorkPath = Join-Path $buildDir "pyi_backend_work"
$backendSpecPath = Join-Path $buildDir "pyi_backend_spec"
$backendEntry = Join-Path $backendDir "run_server.py"
& $venvPython -m PyInstaller `
  --noconfirm `
  --clean `
  --onedir `
  --name NetSimSweeperBackend `
  --distpath $backendDistPath `
  --workpath $backendWorkPath `
  --specpath $backendSpecPath `
  --hidden-import uvicorn.logging `
  --hidden-import uvicorn.loops.auto `
  --hidden-import uvicorn.protocols.http.auto `
  --hidden-import uvicorn.protocols.websockets.auto `
  --hidden-import tkinter `
  --add-data "$frontendDist;frontend_dist" `
  $backendEntry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller backend build failed" }

Write-Step "Building launcher executable (PyInstaller onefile)"
$launcherDistPath = Join-Path $buildDir "launcher_dist"
$launcherWorkPath = Join-Path $buildDir "pyi_launcher_work"
$launcherSpecPath = Join-Path $buildDir "pyi_launcher_spec"
$launcherEntry = Join-Path $packagingDir "launcher\launch_sweeper.py"
& $venvPython -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name NetSimSweeperLauncher `
  --distpath $launcherDistPath `
  --workpath $launcherWorkPath `
  --specpath $launcherSpecPath `
  $launcherEntry
if ($LASTEXITCODE -ne 0) { throw "PyInstaller launcher build failed" }

Write-Step "Assembling portable package layout"
$builtBackendRoot = Join-Path $backendDistPath "NetSimSweeperBackend"
$builtBackendExe = Join-Path $builtBackendRoot "NetSimSweeperBackend.exe"
$builtLauncherExe = Join-Path $launcherDistPath "NetSimSweeperLauncher.exe"
if (-not (Test-Path $builtBackendExe)) {
  throw "Backend executable not found: $builtBackendExe"
}
if (-not (Test-Path $builtLauncherExe)) {
  throw "Launcher executable not found: $builtLauncherExe"
}

Copy-Item -Path $builtLauncherExe -Destination (Join-Path $portableDir "NetSimSweeperLauncher.exe") -Force
Copy-Item -Path $builtBackendRoot -Destination (Join-Path $portableDir "backend") -Recurse -Force

$cmdPath = Join-Path $portableDir "Launch NetSim Sweeper.cmd"
@"
@echo off
setlocal
"%~dp0NetSimSweeperLauncher.exe"
"@ | Set-Content -Path $cmdPath -Encoding ASCII

$portableReadme = Join-Path $portableDir "README_PORTABLE.txt"
@"
NetSim Multi-Parameter Sweeper (Portable)
Version: $Version

How to run:
1. Double-click NetSimSweeperLauncher.exe
   or
2. Double-click Launch NetSim Sweeper.cmd

What it does:
- Starts local backend server on http://127.0.0.1:8090
- Opens the sweeper web UI in your browser

Data location:
- Runtime database and bootstrap artifacts are stored in:
  %LOCALAPPDATA%\NetSimSweeper\
"@ | Set-Content -Path $portableReadme -Encoding ASCII

$portableZip = Join-Path $releaseDir "NetSimSweeper_portable_$Version.zip"
if (Test-Path $portableZip) {
  Remove-Item $portableZip -Force
}
Compress-Archive -Path (Join-Path $portableDir "*") -DestinationPath $portableZip -Force

if (-not $SkipInstaller) {
  Write-Step "Building installer (Inno Setup)"
  $iscc = Get-Command "iscc" -ErrorAction SilentlyContinue
  if (-not $iscc) {
    Write-Warning "Inno Setup compiler (iscc) not found. Installer build skipped."
  } else {
    $issFile = Join-Path $packagingDir "windows\NetSimSweeper.iss"
    & $iscc.Path `
      "/DSourceDir=$portableDir" `
      "/DAppVersion=$Version" `
      "/O$installerOutDir" `
      $issFile
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed" }
  }
}

Write-Step "Release build completed"
Write-Host "Version: $Version"
Write-Host "Portable folder: $portableDir"
Write-Host "Portable zip: $portableZip"
if (-not $SkipInstaller) {
  Write-Host "Installer output directory: $installerOutDir"
}
