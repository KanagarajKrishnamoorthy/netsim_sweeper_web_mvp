# Data Model (MVP)

## Core Types
- `SessionConfig`
  - `scenario_folder`, `netsim_bin_path`, `output_root`
  - `license`: mode (`license_file` / `license_server`) and corresponding value.

- `InputSelection`
  - `parameter_id`
  - `label`
  - `value_spec`:
    - `range`: `start`, `end`, `step`
    - `fixed`: `values[]`
    - `random`: `minimum`, `maximum`, `count`, `seed`
    - `from_file`: `file_path`

- `OutputSelection`
  - `metric_id`
  - `label`
  - optional `row_filters` map.

- `PlannedRun`
  - `run_index`
  - `input_values` map
  - status/timestamps/duration
  - `outputs` map
  - `artifact_dir`, `error_message`

- `SweepJob`
  - identifiers and paths
  - status and progress counters
  - selected inputs/outputs
  - run list
  - warnings

## File-Level Outputs
- `sweep_result.csv`
  - Columns: `run_index`, `status`, selected input labels, selected output labels, `duration_seconds`.
- `run_<n>/input/*`
  - copied scenario input files with patched `Configuration.netsim`.
- `run_<n>/output/*`
  - generated outputs (`Metrics.xml`, traces, logs when live mode is used).

## SQLite Persistence (Current)
- `jobs`
  - `job_id` (PK)
  - `payload_json` (serialized `SweepJob`)
  - `updated_at`
- `job_events`
  - `event_id` (PK autoincrement)
  - `job_id`
  - `event_json` (serialized `EventMessage`)
  - `created_at`

Planned normalization (future):
- split run metadata/inputs/outputs into dedicated relational tables.
