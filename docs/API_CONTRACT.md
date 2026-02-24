# API Contract (MVP)

Base URL: `http://127.0.0.1:8090/api`

## Health
### `GET /health`
Response:
```json
{"status":"ok","timestamp":"2026-02-24T09:00:00.000000"}
```

## Runtime Setup
### `GET /defaults`
Returns server-resolved defaults:
```json
{"default_output_root":"C:\\Users\\<user>\\Documents\\NetSim Multi-Parameter Sweeper"}
```

### `POST /ui/select-folder`
Opens a native folder picker on the server desktop session.
```json
{"title":"Select Scenario Folder","initial_path":"E:\\Codex\\Simulation"}
```
Response:
```json
{"path":"E:\\Codex\\Simulation\\IOT\\LoRaWAN\\Minimal_3_Nodes","selected":true,"message":"Folder selected."}
```

### `POST /ui/select-configuration`
Opens a native file picker restricted to `Configuration.netsim`.
```json
{"title":"Select Configuration.netsim","initial_path":"E:\\Codex\\Simulation\\IOT"}
```
Response uses the same structure as `/ui/select-folder`.

### `POST /ui/select-netsimcore`
Opens a native file picker restricted to `NetSimCore.exe`.
```json
{"title":"Select NetSimCore.exe","initial_path":"E:\\Codex\\NetSimProv15.0.12\\bin_x64"}
```
Response uses the same structure as `/ui/select-folder`.

### `POST /validate/runtime-paths`
Validates exact selected folders (not subfolders) for:
- scenario folder containing direct `Configuration.netsim`
- NetSim executable path (`NetSimCore.exe`) or compatible folder containing direct `NetSimCore.exe`
- output root writability/creatability

## Discovery
### `POST /discover/configurations`
Request:
```json
{"scenario_folder":"E:\\Codex\\MultiParameterSweeperv15.0\\Sample_Configuration"}
```
Response includes all discovered `Configuration.netsim` paths with companion-file flags.

### `POST /discover/parameters/input`
Request:
```json
{"configuration_path":"E:\\...\\Configuration.netsim"}
```
Returns flattened input parameter candidates:
- `parameter_id = "<node_index_path>|<attribute_name>"`
- category, label, current value, value type.

### `POST /discover/parameters/input-hierarchy`
Request:
```json
{"configuration_path":"E:\\...\\Configuration.netsim"}
```
Returns hierarchical input metadata:
- section list (`Device configuration`, `Link configuration`, `Applications configuration`, etc.)
- per-section entity list (device names, links, apps, global nodes)
- per-entity layer groups (`Application`, `Transport`, `Network`, `Interface`, etc.)
- parameters in each layer.

### `POST /discover/parameters/output`
Request:
```json
{
  "configuration_path":"E:\\...\\Configuration.netsim",
  "metrics_path":"E:\\...\\Metrics.xml",
  "generate_metrics_if_missing":true,
  "persist_generated_metrics":false,
  "bootstrap_session":{
    "scenario_folder":"E:\\...\\ScenarioRoot",
    "netsim_bin_path":"C:\\Program Files\\NetSim\\...\\bin_x64\\NetSimCore.exe",
    "output_root":null,
    "license":{
      "mode":"license_server",
      "license_server":"5053@192.168.0.4",
      "license_file_path":null
    }
  }
}
```
Returns output metric candidates with:
- `metric_id = "<menu>|<table>|<column>"`
- row key columns for filter hints.
- log-plugin candidates with `source_type = "log_plugin"` (Packet Trace, Event Trace, App log, LTENR logs).

### `POST /discover/copy-plan`
Request:
```json
{
  "scenario_directory":"E:\\...\\Scenario",
  "include_patterns":["ConfigSupport/*"],
  "exclude_patterns":["*.tmp"]
}
```
Returns files to copy and excluded files.

### `GET /templates/value-file?output_path=<path>`
Generates a CSV template for file-based value mode.

## Jobs
### `POST /jobs`
Creates a sweep job with planned run matrix.

Required body sections:
- `session`: scenario folder, NetSim bin path, output root, license mode/details.
- `configuration_path`
- `input_parameters[]` (with `value_spec`)
- value_spec modes: `fixed`, `range`, `random`, `from_file` (`integer_only` supported for range/random)
- `output_parameters[]`
- `execute_mode` (`dry_run` or `live`)

### `POST /jobs/{job_id}/start`
Starts background execution.

### `POST /jobs/{job_id}/rename`
Renames saved run metadata (display name in dashboard).
```json
{"run_name":"2026-02-24_16-30-10 LoRaWAN Sweep"}
```

### `POST /jobs/{job_id}/resume`
Resets incomplete runs (`pending`, `failed`, `cancelled`, `running`) to `pending` and resumes.

### `POST /jobs/{job_id}/retry-failed`
Resets only failed runs to `pending` and retries them.

### `POST /jobs/{job_id}/cancel`
Requests graceful cancellation.

### `GET /jobs`
List all saved jobs (SQLite-backed persistence).

### `GET /jobs/{job_id}`
Get full job detail including run statuses.

### `GET /jobs/{job_id}/result-csv?limit=250`
Returns CSV headers and first N rows for dashboard preview.

### `POST /jobs/{job_id}/open-result-csv`
Opens the generated `sweep_result.csv` using OS default app.

### `GET /jobs/{job_id}/events`
Server-Sent Events stream.
Each `data:` payload includes:
- `event` (`job_started`, `run_started`, `run_console`, `run_completed`, `job_finished`, ...)
- timestamp and event-specific fields.
