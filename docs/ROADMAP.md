# Implementation Roadmap

## Phase 1 (Done in MVP scaffold)
- API-first backend skeleton.
- XML-based input/output discovery.
- Value expansion modes.
- Copy-plan and run matrix creation.
- Background run executor (`dry_run` + `live` path).
- SSE progress events.
- CSV result logging.

## Phase 2
- Real bootstrap run endpoint to generate `Metrics.xml` automatically. (Done)
- Log-derived output plugins (packet/event/application/LTENR logs). (Done)
- Job resume and retry policy. (Done)
- Run-level validation report with severity categories.

## Phase 3
- Normalized database model and queue workers.
- Multi-user auth and role-based access.
- Rich dashboard analytics (correlation, sensitivity, Pareto).
- Scenario comparison workspace and report export.
