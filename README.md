# NetSim Multi-Parameter Sweeper (Web MVP)

Scientific web utility for running multi-parameter NetSim sweeps with live progress, run logs, plots, and CSV output.

## What This MVP Supports
- Scenario selection by choosing `Configuration.netsim` (file picker restricted to this file name).
- NetSim runtime selection by choosing `NetSimCore.exe` (file picker restricted to this executable).
- Runtime path validation that checks only the selected folder/file directly (no subfolder match fallback).
- Optional `Metrics.xml` bootstrap generation if metrics are missing.
- Input parameter discovery with hierarchy:
  `Device configuration`, `Link configuration`, `Applications configuration`, `Simulation parameters`, `Grid settings`, etc.
- Output metric discovery grouped by section/menu and table.
- Input value modes:
  `fixed list`, `range`, `random`, `from file`.
- Common-property linking mode to apply one value stream across matching parameter labels.
- Cartesian sweep planning with max run guard (`2000` default and server cap).
- Live dashboard:
  progress, per-run duration, console output stream, saved runs, rename run, CSV preview/load, CSV open.
- Plot options:
  separate/combined plots, markers, axis titles, units, SVG/CSV export.
- Persistent saved runs in SQLite.
- Packaged launcher behavior:
  backend auto-stops when all UI sessions close and no job is running.

## Repository Layout
```text
netsim_sweeper_web_mvp/
  backend/                 FastAPI backend + run engine
  frontend/                React + Vite UI
  docs/                    Architecture, API contract, data model, roadmap
  packaging/launcher/      Windows launcher source
  packaging/windows/       Inno Setup script
  build_release.ps1        Portable + installer build script
  release/                 Generated artifacts
```

## Prerequisites
- Windows 10/11
- NetSim installation with `NetSimCore.exe`
- Valid NetSim license (server or file)
- Python 3.11-3.13 recommended for build workflows
- Node.js 18+ and npm
- Optional: Inno Setup 6 for installer creation

## Development Run
1. Start backend:
```powershell
cd .\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run_server.py
```

2. Start frontend (new terminal):
```powershell
cd .\frontend
npm install
npm run dev
```

3. Open UI:
- Frontend dev URL: `http://127.0.0.1:5175`
- Backend API base: `http://127.0.0.1:8090/api`

## Build Portable and Installer
From project root:
```powershell
powershell -ExecutionPolicy Bypass -File .\build_release.ps1
```

Outputs:
- Portable zip:
  `release\NetSimSweeper_portable_0.1.0.zip`
- Portable folder:
  `release\portable\NetSimSweeper\`
- Installer:
  `release\installer\NetSimSweeperSetup_0.1.0.exe`

If `iscc` is not in PATH, compile installer manually:
```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" `
  "/DSourceDir=<absolute_path_to_release\portable\NetSimSweeper>" `
  "/DAppVersion=0.1.0" `
  "/O<absolute_path_to_release\installer>" `
  ".\packaging\windows\NetSimSweeper.iss"
```

## Run Packaged Utility
- Launch:
  `NetSimSweeperLauncher.exe` (or `Launch NetSim Sweeper.cmd`)
- Launcher behavior:
  starts backend on `127.0.0.1:8090`, opens browser UI, suppresses console noise.
- Auto shutdown behavior:
  backend exits after UI closes when no run is active.

## Data and Artifacts
- Persistent app data:
  `%LOCALAPPDATA%\NetSimSweeper\`
- Job database:
  `%LOCALAPPDATA%\NetSimSweeper\jobs.db`
- Default output root:
  `%USERPROFILE%\Documents\NetSim Multi-Parameter Sweeper\`
- Default run name:
  timestamp folder format `YYYY-MM-DD_HH-MM-SS` (renamable in dashboard)
- Per-job CSV:
  `...<run>\job_<job_id>\sweep_result.csv`

## Runtime Configuration Variables
Use `backend\.env.example` as reference.

| Variable | Default | Purpose |
|---|---|---|
| `NETSIM_SWEEPER_HOST` | `127.0.0.1` | Backend bind host |
| `NETSIM_SWEEPER_PORT` | `8090` | Backend port |
| `NETSIM_SWEEPER_MAX_RUNS` | `2000` | Server-side max runs cap |
| `NETSIM_SWEEPER_DEFAULT_OUTPUT_ROOT` | empty | Override default output root |
| `NETSIM_SWEEPER_APPDATA_DIR` | empty | Override app data directory |
| `NETSIM_SWEEPER_FRONTEND_DIST` | empty | Override bundled frontend dist path |
| `NETSIM_SWEEPER_AUTO_SHUTDOWN_ON_UI_CLOSE` | `0` | Auto-stop backend on UI close |
| `NETSIM_SWEEPER_UI_HEARTBEAT_TTL_SECONDS` | `25` | UI session TTL |
| `NETSIM_SWEEPER_IDLE_SHUTDOWN_GRACE_SECONDS` | `45` | Startup grace before idle shutdown |

## Troubleshooting
- `http://127.0.0.1:5175` not loading:
  this URL is for frontend dev mode only; packaged app serves UI on `http://127.0.0.1:8090/`.
- Buttons not responding:
  confirm backend is running and reachable at `http://127.0.0.1:8090/api/health`.
- Backend does not stop on browser close:
  launch via `NetSimSweeperLauncher.exe` so auto-shutdown environment is applied.
- Native browse dialogs not opening:
  run in a normal desktop user session (not headless service context).

## Additional Technical Docs
- [Architecture](./docs/ARCHITECTURE.md)
- [API Contract](./docs/API_CONTRACT.md)
- [Data Model](./docs/DATA_MODEL.md)
- [Roadmap](./docs/ROADMAP.md)
