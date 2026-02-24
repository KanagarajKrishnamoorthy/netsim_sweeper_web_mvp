# NetSim Multi-Parameter Sweeper Web Utility Architecture

## 1. Objective
Build a scientific web utility that:
- Discovers sweepable input parameters from `Configuration.netsim`.
- Discovers output metrics from `Metrics.xml` and optional log extractors.
- Plans and executes sweep runs with reproducible artifacts.
- Provides live status, run timing, dynamic plots, and CSV logging.

## 2. System Layout
### Backend (`FastAPI`)
- `app/api/routes.py`
  - Discovery APIs, copy plan API, job lifecycle APIs, SSE event stream.
- `app/services/xml_discovery.py`
  - Parses config parameters and metrics table/columns.
  - Applies parameter updates to copied config per run.
- `app/services/netsim_exec.py`
  - NetSim process invocation and bootstrap metrics generation.
- `app/services/log_plugins.py`
  - Plugin registry for log-derived output metrics.
- `app/services/value_specs.py`
  - Expands value specs: range, fixed list, random, from file.
- `app/services/file_plan.py`
  - Differentiates likely input files vs output/generated files.
- `app/services/runner.py`
  - Builds run matrix, executes dry-run/live run loop, writes result CSV.
- `app/services/job_store.py`
  - Job state manager with SQLite-backed persistence and live cancellation state.
- `app/services/persistence.py`
  - SQLite repository for jobs and event stream.

### Frontend (`React + Vite`)
- Setup wizard for scenario selection and runtime configuration.
- Input/output selector panels with filter/search.
- Sweep launch and dashboard.
- SSE-based live progress updates.

## 3. Run Lifecycle
1. Discover scenario configs from a user folder.
2. Select one `Configuration.netsim`.
3. Discover input candidates from XML attributes.
4. Discover output candidates from `Metrics.xml`.
   - If `Metrics.xml` is absent and enabled, run bootstrap simulation to generate it.
   - Include log-plugin output candidates.
5. Configure value specs and output metric list.
6. Build copy plan and validate.
7. Create job (run matrix generation).
8. Start job:
   - Per run: create run folder, copy input files, patch config values.
   - Execute NetSim (`live`) or mock execution (`dry_run`).
   - Parse selected output metrics.
   - Append run row to `sweep_result.csv`.
9. Stream run events and update UI plots in real time.

## 4. Folder/Artifact Convention
Default output root:
`%USERPROFILE%\Documents\NetSim Multi-Parameter Sweeper\`

Per job:
- `job_<id>/`
- `sweep_result.csv`
- `run_0001/input/...`
- `run_0001/output/Metrics.xml`

## 5. File Copy Policy
Default copy behavior:
- Copy all files under scenario directory except default output-like patterns:
  - `Metrics.xml`, `result.csv`, `Packet Trace.csv`, `Event Trace.csv`,
  - `*.pcap`, `*.log`, `*Log*.txt`, `log/*`, `*Result*.csv`, `kpi*.csv`.
- User can override with include/exclude patterns.

## 6. Requirement Coverage
1. Any folder input with `Configuration.netsim`: supported by discovery API.
2. NetSim binary and license options: part of session config.
3. Output location default: supported; timestamped job directories.
4. Mandatory config + optional metrics: supported with warning path for bootstrap.
5. Category-wise input parameters: supported.
6. Table-wise output metrics + future log extractors: metrics supported now.
7. Range/fixed/random/file value modes: supported.
8. Validation + copy preview + selective file control: supported.
9. Progress/time/plot updates: progress and timings via SSE in MVP.
10. CSV log of inputs and outputs: supported per run.

## 7. MVP Boundaries
- Persistence is currently JSON-in-row SQLite (not fully normalized relational schema).
- Bootstrap metrics generation requires valid NetSim runtime/license.
- Live execution assumes valid `NetSimcore.exe` and license.

## 8. Next Production Steps
- Normalize persistence schema (`runs`, `run_outputs`, `artifacts` tables).
- Add optional PostgreSQL backend for multi-user deployments.
- Add worker queue (Celery/RQ) for resilient execution.
- Add richer derived metrics plugin framework from trace logs.
- Add run deduplication and scheduling policies.
