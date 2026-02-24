from __future__ import annotations

import csv
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from app.models.schemas import (
    ExecuteMode,
    InputSelection,
    JobStatus,
    OutputMetricCandidate,
    OutputSelection,
    PlannedRun,
    RunStatus,
    SweepJob,
    SweepJobCreateRequest,
)
from app.services.file_plan import build_copy_plan
from app.services.job_store import job_store
from app.services.log_plugins import extract_log_metrics, log_metric_ids, mock_log_metric_value
from app.services.netsim_exec import resolve_netsimcore_path, run_netsim_once
from app.services.value_specs import plan_parameter_combinations
from app.services.xml_discovery import (
    create_mock_metrics_file,
    parse_input_parameters,
    parse_metrics_value,
    parse_output_metrics,
    set_parameter_value,
)


def _timestamp_folder() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _recompute_counters(job: SweepJob) -> None:
    job.completed_run_count = sum(1 for run in job.runs if run.status == RunStatus.completed)
    job.failed_run_count = sum(1 for run in job.runs if run.status == RunStatus.failed)
    job.cancelled_run_count = sum(1 for run in job.runs if run.status == RunStatus.cancelled)


def _resolve_job_status(job: SweepJob) -> JobStatus:
    has_pending = any(run.status in {RunStatus.pending, RunStatus.running} for run in job.runs)
    if has_pending:
        if job_store.is_cancel_requested(job.job_id):
            return JobStatus.cancelled
        return JobStatus.draft
    if job.failed_run_count > 0:
        return JobStatus.failed
    if job.cancelled_run_count > 0:
        return JobStatus.cancelled
    return JobStatus.completed


def _reset_run_for_retry(run: PlannedRun) -> None:
    run.status = RunStatus.pending
    run.started_at = None
    run.completed_at = None
    run.duration_seconds = None
    run.outputs = {}
    run.error_message = None


def prepare_job_for_resume(job: SweepJob, only_failed: bool = False) -> SweepJob:
    changed = False
    for run in job.runs:
        if only_failed:
            if run.status == RunStatus.failed:
                _reset_run_for_retry(run)
                changed = True
            continue
        if run.status in {RunStatus.failed, RunStatus.cancelled, RunStatus.running}:
            _reset_run_for_retry(run)
            changed = True
        elif run.status == RunStatus.pending:
            changed = True

    if not changed:
        mode = "failed runs" if only_failed else "incomplete runs"
        raise ValueError(f"No {mode} available to resume.")

    job.status = JobStatus.draft
    _recompute_counters(job)
    return job


def build_job(request: SweepJobCreateRequest, max_runs_cap: int) -> SweepJob:
    if request.max_runs > max_runs_cap:
        raise ValueError(f"max_runs cannot exceed server cap {max_runs_cap}")

    configuration_path = Path(request.configuration_path).resolve()
    scenario_directory = configuration_path.parent
    output_root = (
        Path(request.session.output_root).expanduser().resolve()
        if request.session.output_root
        else Path.home().joinpath("Documents", "NetSim Multi-Parameter Sweeper").resolve()
    )
    job_id = uuid.uuid4().hex[:12]
    run_name = _timestamp_folder()
    job_output_dir = output_root / run_name / f"job_{job_id}"
    job_output_dir.mkdir(parents=True, exist_ok=True)
    result_csv = job_output_dir / "sweep_result.csv"

    combinations = plan_parameter_combinations(
        request.input_parameters,
        max_runs=request.max_runs,
    )
    planned_runs = [PlannedRun(run_index=i + 1, input_values=combo) for i, combo in enumerate(combinations)]

    build_copy_plan(
        scenario_directory=scenario_directory,
        include_patterns=request.include_patterns,
        exclude_patterns=request.exclude_patterns,
    )

    warnings: list[str] = []
    if request.execute_mode == ExecuteMode.live:
        try:
            resolve_netsimcore_path(request.session.netsim_bin_path)
        except RuntimeError:
            warnings.append(
                "execute_mode=live requested but NetSimCore.exe path is invalid. "
                "Runs will fail unless the path is corrected."
            )

    resolved_metrics_path: str | None = request.metrics_path
    if resolved_metrics_path is None:
        inferred = scenario_directory / "Metrics.xml"
        if inferred.exists():
            resolved_metrics_path = str(inferred)

    job = SweepJob(
        job_id=job_id,
        run_name=run_name,
        created_at=datetime.utcnow(),
        status=JobStatus.draft,
        session=request.session,
        configuration_path=str(configuration_path),
        metrics_path=resolved_metrics_path,
        output_directory=str(job_output_dir),
        input_parameters=request.input_parameters,
        output_parameters=request.output_parameters,
        include_patterns=request.include_patterns,
        exclude_patterns=request.exclude_patterns,
        execute_mode=request.execute_mode,
        planned_run_count=len(planned_runs),
        result_csv_path=str(result_csv),
        runs=planned_runs,
        warnings=warnings,
    )
    _recompute_counters(job)
    return job


def _write_job_csv_snapshot(job: SweepJob) -> None:
    path = Path(job.result_csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    input_map = {selection.parameter_id: selection.label for selection in job.input_parameters}
    output_map = {selection.metric_id: selection.label for selection in job.output_parameters}
    header = ["run_index", "status", *input_map.values(), *output_map.values(), "duration_seconds"]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for run in sorted(job.runs, key=lambda item: item.run_index):
            input_values = [run.input_values.get(param_id, "") for param_id in input_map.keys()]
            output_values = [run.outputs.get(metric_id, "") for metric_id in output_map.keys()]
            writer.writerow(
                [
                    run.run_index,
                    run.status,
                    *input_values,
                    *output_values,
                    run.duration_seconds if run.duration_seconds is not None else "",
                ]
            )


def _copy_selected_files(job: SweepJob, run_input_dir: Path) -> None:
    scenario_directory = Path(job.configuration_path).parent
    copy_items, _ = build_copy_plan(
        scenario_directory=scenario_directory,
        include_patterns=job.include_patterns,
        exclude_patterns=job.exclude_patterns,
    )
    for item in copy_items:
        src = scenario_directory / item.relative_path
        dst = run_input_dir / item.relative_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _copy_tree_files(src_root: Path, dst_root: Path) -> None:
    for src in src_root.rglob("*"):
        rel = src.relative_to(src_root)
        dst = dst_root / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _mock_metric_candidates_from_outputs(selections: list[OutputSelection]) -> list[OutputMetricCandidate]:
    items: list[OutputMetricCandidate] = []
    for selection in selections:
        if selection.source_type != "metrics_xml":
            continue
        menu_name, table_name, column_name = selection.metric_id.split("|", 2)
        items.append(
            OutputMetricCandidate(
                metric_id=selection.metric_id,
                source_type="metrics_xml",
                menu_name=menu_name,
                table_name=table_name,
                column_name=column_name,
            )
        )
    return items


def _execute_run(job: SweepJob, run: PlannedRun) -> None:
    run_dir = Path(job.output_directory) / f"run_{run.run_index:04d}"
    run_input_dir = run_dir / "input"
    run_output_dir = run_dir / "output"
    run_input_dir.mkdir(parents=True, exist_ok=True)
    run_output_dir.mkdir(parents=True, exist_ok=True)
    run.artifact_dir = str(run_dir)

    _copy_selected_files(job, run_input_dir)

    input_config_path = run_input_dir / "Configuration.netsim"
    if not input_config_path.exists():
        shutil.copy2(job.configuration_path, input_config_path)
    set_parameter_value(
        configuration_path=input_config_path,
        updates=run.input_values,
        output_path=input_config_path,
    )

    metrics_path = run_output_dir / "Metrics.xml"
    if job.execute_mode == ExecuteMode.live:
        io_dir = run_output_dir
        _copy_tree_files(run_input_dir, io_dir)
        console_log = io_dir / "netsim_console.log"
        console_log.parent.mkdir(parents=True, exist_ok=True)

        def _emit_console(line: str) -> None:
            with console_log.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            job_store.append_event(
                job.job_id,
                "run_console",
                {"run_index": run.run_index, "line": line},
            )

        run_netsim_once(session=job.session, io_dir=io_dir, on_console=_emit_console)
        produced = io_dir / "Metrics.xml"
        if produced.exists() and produced != metrics_path:
            shutil.copy2(produced, metrics_path)
    else:
        job_store.append_event(
            job.job_id,
            "run_console",
            {"run_index": run.run_index, "line": "[dry_run] Preparing synthetic outputs..."},
        )
        time.sleep(0.2)
        if job.metrics_path and Path(job.metrics_path).exists():
            metric_candidates = parse_output_metrics(Path(job.metrics_path))
        else:
            metric_candidates = _mock_metric_candidates_from_outputs(job.output_parameters)
        create_mock_metrics_file(metrics_path, metric_candidates)
        job_store.append_event(
            job.job_id,
            "run_console",
            {"run_index": run.run_index, "line": "[dry_run] Synthetic Metrics.xml generated."},
        )

    extracted_log_values = extract_log_metrics(run_output_dir)
    outputs: dict[str, str | float | int | None] = {}
    for selection in job.output_parameters:
        value: str | float | int | None = None
        if selection.source_type == "metrics_xml":
            if metrics_path.exists():
                value = parse_metrics_value(
                    metrics_path=metrics_path,
                    metric_id=selection.metric_id,
                    row_filters=selection.row_filters,
                )
        elif selection.source_type == "log_plugin":
            if job.execute_mode == ExecuteMode.dry_run:
                value = mock_log_metric_value(selection.metric_id, run.run_index)
            else:
                value = extracted_log_values.get(selection.metric_id)
        outputs[selection.metric_id] = value
    run.outputs = outputs


def run_job(job_id: str, pending_only: bool = True) -> None:
    job = job_store.get(job_id)
    if job is None:
        return

    try:
        job_store.clear_cancel(job_id)
        _recompute_counters(job)
        job.status = JobStatus.running
        job_store.update(job)
        job_store.append_event(job.job_id, "job_started", {"job_id": job.job_id, "pending_only": pending_only})
        _write_job_csv_snapshot(job)

        for run in job.runs:
            if pending_only and run.status != RunStatus.pending:
                continue
            if not pending_only and run.status == RunStatus.completed:
                continue

            if job_store.is_cancel_requested(job.job_id):
                for tail in job.runs:
                    if tail.status == RunStatus.pending:
                        tail.status = RunStatus.cancelled
                _recompute_counters(job)
                _write_job_csv_snapshot(job)
                job_store.update(job)
                break

            started = datetime.utcnow()
            run.started_at = started
            run.status = RunStatus.running
            job_store.update(job)
            job_store.append_event(
                job.job_id,
                "run_started",
                {"run_index": run.run_index, "planned": job.planned_run_count},
            )

            try:
                _execute_run(job, run)
                run.status = RunStatus.completed
            except Exception as exc:
                run.status = RunStatus.failed
                run.error_message = str(exc)

            completed = datetime.utcnow()
            run.completed_at = completed
            run.duration_seconds = (completed - started).total_seconds()
            _recompute_counters(job)
            _write_job_csv_snapshot(job)
            job_store.update(job)
            job_store.append_event(
                job.job_id,
                "run_completed",
                {
                    "run_index": run.run_index,
                    "status": run.status,
                    "duration_seconds": run.duration_seconds,
                    "completed_runs": job.completed_run_count,
                    "failed_runs": job.failed_run_count,
                    "cancelled_runs": job.cancelled_run_count,
                },
            )

        _recompute_counters(job)
        job.status = _resolve_job_status(job)
        job_store.update(job)
        job_store.append_event(
            job.job_id,
            "job_finished",
            {
                "status": job.status,
                "completed_runs": job.completed_run_count,
                "failed_runs": job.failed_run_count,
                "cancelled_runs": job.cancelled_run_count,
            },
        )
    except Exception as exc:
        job.status = JobStatus.failed
        job.warnings.append(f"Runner fatal error: {exc}")
        _recompute_counters(job)
        _write_job_csv_snapshot(job)
        job_store.update(job)
        job_store.append_event(job.job_id, "job_failed", {"error": str(exc)})


def start_job_in_background(job_id: str, pending_only: bool = True) -> None:
    thread = threading.Thread(target=run_job, args=(job_id, pending_only), daemon=True)
    thread.start()


def validate_parameter_ids(configuration_path: Path, parameter_ids: list[str]) -> None:
    available = {candidate.parameter_id for candidate in parse_input_parameters(configuration_path)}
    missing = [param_id for param_id in parameter_ids if param_id not in available]
    if missing:
        raise ValueError(f"Unknown parameter_id values: {missing[:5]}")


def validate_input_selections(configuration_path: Path, input_selections: list[InputSelection]) -> None:
    available = {candidate.parameter_id for candidate in parse_input_parameters(configuration_path)}
    missing: list[str] = []
    duplicates: set[str] = set()
    seen: set[str] = set()
    for selection in input_selections:
        ids = [selection.parameter_id, *getattr(selection, "apply_to_parameter_ids", [])]
        for key in ids:
            if key not in available:
                missing.append(key)
            if key in seen:
                duplicates.add(key)
            seen.add(key)
    if missing:
        raise ValueError(f"Unknown parameter_id values: {missing[:5]}")
    if duplicates:
        dup_list = sorted(duplicates)
        raise ValueError(f"Duplicate parameter assignment found: {dup_list[:5]}")


def validate_output_ids(
    configuration_path: Path,
    metrics_path: Path | None,
    output_selections: list[OutputSelection],
) -> None:
    valid_metrics_ids: set[str] = set()
    if metrics_path and metrics_path.exists():
        valid_metrics_ids = {candidate.metric_id for candidate in parse_output_metrics(metrics_path)}
    valid_log_ids = log_metric_ids()

    missing_metrics: list[str] = []
    missing_logs: list[str] = []
    for selection in output_selections:
        if selection.source_type == "metrics_xml":
            if valid_metrics_ids and selection.metric_id not in valid_metrics_ids:
                missing_metrics.append(selection.metric_id)
        elif selection.source_type == "log_plugin":
            if selection.metric_id not in valid_log_ids:
                missing_logs.append(selection.metric_id)

    if missing_metrics:
        raise ValueError(f"Unknown metrics_xml metric_id values: {missing_metrics[:5]}")
    if missing_logs:
        raise ValueError(f"Unknown log_plugin metric_id values: {missing_logs[:5]}")
