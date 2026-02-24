from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.core.config import settings
from app.models.schemas import (
    CancelJobResponse,
    DiscoverConfigurationsRequest,
    DiscoverConfigurationsResponse,
    DiscoverInputHierarchyRequest,
    DiscoverInputHierarchyResponse,
    DiscoverInputParametersRequest,
    DiscoverInputParametersResponse,
    DefaultsResponse,
    DiscoverOutputParametersRequest,
    DiscoverOutputParametersResponse,
    FilePlanRequest,
    FilePlanResponse,
    JobStatus,
    JobListResponse,
    RenameJobRequest,
    RenameJobResponse,
    ResultCsvResponse,
    SelectFolderRequest,
    SelectFolderResponse,
    StartJobResponse,
    SweepJob,
    SweepJobCreateRequest,
    UiSessionRequest,
    UiSessionResponse,
    ValidateRuntimePathsRequest,
    ValidateRuntimePathsResponse,
)
from app.services.file_plan import DEFAULT_OUTPUT_PATTERNS, build_copy_plan
from app.services.job_store import job_store
from app.services.log_plugins import available_log_metric_candidates
from app.services.netsim_exec import generate_bootstrap_metrics
from app.services.runtime_guard import runtime_guard
from app.services.runner import (
    build_job,
    prepare_job_for_resume,
    start_job_in_background,
    validate_input_selections,
    validate_output_ids,
)
from app.services.ui_dialog import select_configuration_file, select_directory, select_netsimcore_file
from app.services.validation import (
    validate_netsim_bin_folder,
    validate_output_root,
    validate_scenario_folder,
)
from app.services.xml_discovery import (
    ensure_metrics_file,
    find_configuration_files,
    parse_input_hierarchy,
    parse_input_parameters,
    parse_output_metrics,
    write_value_template_csv,
)

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "runtime_guard_enabled": runtime_guard.enabled,
        "active_ui_sessions": runtime_guard.active_session_count(),
    }


@router.get("/defaults", response_model=DefaultsResponse)
def defaults() -> DefaultsResponse:
    return DefaultsResponse(default_output_root=str(settings.resolved_default_output_root()))


@router.post("/runtime/ui-heartbeat", response_model=UiSessionResponse)
def runtime_ui_heartbeat(request: UiSessionRequest) -> UiSessionResponse:
    result = runtime_guard.heartbeat(request.session_id)
    return UiSessionResponse(**result)


@router.post("/runtime/ui-disconnect", response_model=UiSessionResponse)
def runtime_ui_disconnect(request: UiSessionRequest) -> UiSessionResponse:
    result = runtime_guard.disconnect(request.session_id)
    return UiSessionResponse(**result)


@router.post("/ui/select-folder", response_model=SelectFolderResponse)
def select_folder_dialog(request: SelectFolderRequest) -> SelectFolderResponse:
    try:
        selected = select_directory(title=request.title, initial_path=request.initial_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Folder picker failed: {exc}") from exc
    if selected is None:
        return SelectFolderResponse(path=None, selected=False, message="User cancelled folder selection.")
    return SelectFolderResponse(path=selected, selected=True, message="Folder selected.")


@router.post("/ui/select-configuration", response_model=SelectFolderResponse)
def select_configuration_dialog(request: SelectFolderRequest) -> SelectFolderResponse:
    try:
        selected = select_configuration_file(title=request.title, initial_path=request.initial_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Configuration picker failed: {exc}") from exc
    if selected is None:
        return SelectFolderResponse(
            path=None,
            selected=False,
            message="No Configuration.netsim selected (or selection cancelled).",
        )
    return SelectFolderResponse(path=selected, selected=True, message="Configuration.netsim selected.")


@router.post("/ui/select-netsimcore", response_model=SelectFolderResponse)
def select_netsimcore_dialog(request: SelectFolderRequest) -> SelectFolderResponse:
    try:
        selected = select_netsimcore_file(title=request.title, initial_path=request.initial_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"NetSimCore picker failed: {exc}") from exc
    if selected is None:
        return SelectFolderResponse(
            path=None,
            selected=False,
            message="No NetSimCore.exe selected (or selection cancelled).",
        )
    return SelectFolderResponse(path=selected, selected=True, message="NetSimCore.exe selected.")


@router.post("/validate/runtime-paths", response_model=ValidateRuntimePathsResponse)
def validate_runtime_paths(request: ValidateRuntimePathsRequest) -> ValidateRuntimePathsResponse:
    scenario = validate_scenario_folder(request.scenario_folder)
    netsim = validate_netsim_bin_folder(request.netsim_bin_path)
    output = validate_output_root(
        request.output_root if request.output_root else str(settings.resolved_default_output_root())
    )
    all_valid = scenario.valid and netsim.valid and output.valid
    return ValidateRuntimePathsResponse(
        scenario_folder=scenario,
        netsim_bin_path=netsim,
        output_root=output,
        all_valid=all_valid,
    )


@router.post("/discover/configurations", response_model=DiscoverConfigurationsResponse)
def discover_configurations(request: DiscoverConfigurationsRequest) -> DiscoverConfigurationsResponse:
    folder = Path(request.scenario_folder).expanduser().resolve()
    if not folder.exists():
        raise HTTPException(status_code=400, detail=f"Folder does not exist: {folder}")
    configs = find_configuration_files(folder)
    items = []
    for cfg in configs:
        directory = cfg.parent
        items.append(
            {
                "configuration_path": str(cfg),
                "directory": str(directory),
                "has_metrics_xml": (directory / "Metrics.xml").exists(),
                "has_protocol_logs_config": (directory / "ProtocolLogsConfig.txt").exists(),
                "has_plot_info": (directory / "PlotInfo.txt").exists(),
                "has_config_support": (directory / "ConfigSupport").exists(),
            }
        )
    return DiscoverConfigurationsResponse(count=len(items), items=items)


@router.post("/discover/parameters/input", response_model=DiscoverInputParametersResponse)
def discover_input_parameters(
    request: DiscoverInputParametersRequest,
) -> DiscoverInputParametersResponse:
    config_path = Path(request.configuration_path).expanduser().resolve()
    if not config_path.exists():
        raise HTTPException(status_code=400, detail=f"Configuration file not found: {config_path}")
    items = parse_input_parameters(config_path)
    categories = sorted({item.category for item in items})
    return DiscoverInputParametersResponse(
        configuration_path=str(config_path),
        count=len(items),
        categories=categories,
        items=items,
    )


@router.post("/discover/parameters/input-hierarchy", response_model=DiscoverInputHierarchyResponse)
def discover_input_hierarchy(
    request: DiscoverInputHierarchyRequest,
) -> DiscoverInputHierarchyResponse:
    config_path = Path(request.configuration_path).expanduser().resolve()
    if not config_path.exists():
        raise HTTPException(status_code=400, detail=f"Configuration file not found: {config_path}")
    sections = parse_input_hierarchy(config_path)
    return DiscoverInputHierarchyResponse(
        configuration_path=str(config_path),
        section_count=len(sections),
        sections=sections,
    )


@router.post("/discover/parameters/output", response_model=DiscoverOutputParametersResponse)
def discover_output_parameters(
    request: DiscoverOutputParametersRequest,
) -> DiscoverOutputParametersResponse:
    warnings: list[str] = []
    metrics_path: Path | None = None
    scenario_dir: Path | None = None
    if request.configuration_path:
        scenario_dir = Path(request.configuration_path).expanduser().resolve().parent

    if request.metrics_path:
        metrics_path = Path(request.metrics_path).expanduser().resolve()
    if not metrics_path and request.configuration_path:
        config_path = Path(request.configuration_path).expanduser().resolve()
        metrics_path, inferred_warnings = ensure_metrics_file(config_path, None)
        warnings.extend(inferred_warnings)
    if (
        not metrics_path
        and request.generate_metrics_if_missing
        and request.configuration_path
        and request.bootstrap_session is not None
    ):
        config_path = Path(request.configuration_path).expanduser().resolve()
        try:
            metrics_path = generate_bootstrap_metrics(
                configuration_path=config_path,
                session=request.bootstrap_session,
                persist_generated_metrics=request.persist_generated_metrics,
            )
            warnings.append("Metrics.xml was generated via a temporary bootstrap run.")
        except Exception as exc:
            warnings.append(f"Bootstrap run failed: {exc}")

    all_items = []
    if metrics_path and metrics_path.exists():
        all_items.extend(parse_output_metrics(metrics_path))
    if request.generate_metrics_if_missing:
        if not request.bootstrap_session and not (metrics_path and metrics_path.exists()):
            warnings.append(
                "Metrics generation requested, but bootstrap_session was not provided. "
                "Set runtime details and retry."
            )

    if scenario_dir and scenario_dir.exists():
        all_items.extend(available_log_metric_candidates(scenario_dir))

    menu_names = sorted({item.menu_name for item in all_items})
    return DiscoverOutputParametersResponse(
        metrics_path=str(metrics_path) if metrics_path and metrics_path.exists() else None,
        count=len(all_items),
        menu_names=menu_names,
        items=all_items,
        warnings=warnings,
    )


@router.post("/discover/copy-plan", response_model=FilePlanResponse)
def discover_copy_plan(request: FilePlanRequest) -> FilePlanResponse:
    scenario_directory = Path(request.scenario_directory).expanduser().resolve()
    if not scenario_directory.exists():
        raise HTTPException(status_code=400, detail=f"Scenario directory not found: {scenario_directory}")
    copy_items, excluded_items = build_copy_plan(
        scenario_directory=scenario_directory,
        include_patterns=request.include_patterns,
        exclude_patterns=request.exclude_patterns,
    )
    return FilePlanResponse(
        scenario_directory=str(scenario_directory),
        include_patterns=request.include_patterns,
        exclude_patterns=DEFAULT_OUTPUT_PATTERNS + request.exclude_patterns,
        copy_count=len(copy_items),
        excluded_count=len(excluded_items),
        copy_items=copy_items,
        excluded_items=excluded_items,
    )


@router.get("/templates/value-file", response_class=PlainTextResponse)
def generate_value_template(output_path: str | None = None) -> str:
    if output_path:
        path = Path(output_path).expanduser().resolve()
    else:
        path = Path.cwd() / "value_template.csv"
    created = write_value_template_csv(path)
    return str(created)


@router.post("/jobs", response_model=SweepJob)
def create_job(request: SweepJobCreateRequest) -> SweepJob:
    config_path = Path(request.configuration_path).expanduser().resolve()
    if not config_path.exists():
        raise HTTPException(status_code=400, detail=f"Configuration file not found: {config_path}")
    metrics_path = Path(request.metrics_path).resolve() if request.metrics_path else None
    if metrics_path is None:
        inferred = config_path.parent / "Metrics.xml"
        metrics_path = inferred if inferred.exists() else None

    try:
        validate_input_selections(
            configuration_path=config_path,
            input_selections=request.input_parameters,
        )
        validate_output_ids(
            configuration_path=config_path,
            metrics_path=metrics_path,
            output_selections=request.output_parameters,
        )
        job = build_job(request=request, max_runs_cap=settings.max_runs)
        job_store.create(job)
        return job
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs", response_model=JobListResponse)
def list_jobs() -> JobListResponse:
    return JobListResponse(jobs=job_store.list_jobs())


@router.get("/jobs/{job_id}", response_model=SweepJob)
def get_job(job_id: str) -> SweepJob:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    return job


@router.post("/jobs/{job_id}/rename", response_model=RenameJobResponse)
def rename_job(job_id: str, request: RenameJobRequest) -> RenameJobResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    run_name = request.run_name.strip()
    if not run_name:
        raise HTTPException(status_code=400, detail="run_name cannot be empty.")
    if len(run_name) > 120:
        raise HTTPException(status_code=400, detail="run_name cannot exceed 120 characters.")
    job.run_name = run_name
    job_store.update(job)
    job_store.append_event(job_id, "job_renamed", {"run_name": run_name})
    return RenameJobResponse(job_id=job_id, run_name=run_name, message="Run renamed.")


@router.get("/jobs/{job_id}/result-csv", response_model=ResultCsvResponse)
def get_result_csv(job_id: str, limit: int = 250) -> ResultCsvResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    csv_path = Path(job.result_csv_path)
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"Result CSV does not exist yet: {csv_path}")
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        import csv

        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        return ResultCsvResponse(headers=[], rows=[], total_rows=0)
    headers = rows[0]
    data = rows[1:]
    return ResultCsvResponse(headers=headers, rows=data[: max(limit, 1)], total_rows=len(data))


@router.post("/jobs/{job_id}/open-result-csv", response_model=StartJobResponse)
def open_result_csv(job_id: str) -> StartJobResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    csv_path = Path(job.result_csv_path)
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"Result CSV does not exist yet: {csv_path}")
    try:
        import os

        os.startfile(str(csv_path))  # type: ignore[attr-defined]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open CSV file: {exc}") from exc
    return StartJobResponse(job_id=job_id, status=job.status, message=f"Opened {csv_path.name}")


@router.post("/jobs/{job_id}/start", response_model=StartJobResponse)
def start_job(job_id: str) -> StartJobResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    if job.status != JobStatus.draft:
        raise HTTPException(status_code=409, detail=f"Job is already {job.status}")
    start_job_in_background(job_id=job_id, pending_only=True)
    return StartJobResponse(job_id=job_id, status="running", message="Job started")


@router.post("/jobs/{job_id}/resume", response_model=StartJobResponse)
def resume_job(job_id: str) -> StartJobResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    if job.status == JobStatus.running:
        raise HTTPException(status_code=409, detail=f"Job is already {job.status}")
    try:
        resumed = prepare_job_for_resume(job=job, only_failed=False)
        job_store.update(resumed)
        job_store.append_event(job_id, "job_resumed", {"mode": "resume_incomplete"})
        start_job_in_background(job_id=job_id, pending_only=True)
        return StartJobResponse(job_id=job_id, status="running", message="Resume started")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/retry-failed", response_model=StartJobResponse)
def retry_failed_job(job_id: str) -> StartJobResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    if job.status == JobStatus.running:
        raise HTTPException(status_code=409, detail=f"Job is already {job.status}")
    try:
        resumed = prepare_job_for_resume(job=job, only_failed=True)
        job_store.update(resumed)
        job_store.append_event(job_id, "job_resumed", {"mode": "retry_failed"})
        start_job_in_background(job_id=job_id, pending_only=True)
        return StartJobResponse(job_id=job_id, status="running", message="Retry failed started")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/cancel", response_model=CancelJobResponse)
def cancel_job(job_id: str) -> CancelJobResponse:
    if not job_store.request_cancel(job_id):
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    return CancelJobResponse(job_id=job_id, status="cancelled", message="Cancel requested")


@router.get("/jobs/{job_id}/events")
def stream_job_events(job_id: str) -> StreamingResponse:
    if job_store.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")

    def generate() -> Iterator[str]:
        cursor = 0
        idle_cycles = 0
        while True:
            events, cursor = job_store.get_events_since(job_id, cursor)
            if events:
                idle_cycles = 0
                for event in events:
                    payload = {"event": event.event, "timestamp": event.timestamp.isoformat(), **event.payload}
                    yield f"data: {json.dumps(payload)}\n\n"
            else:
                idle_cycles += 1
                if idle_cycles > 600:
                    return
                time.sleep(0.5)

    return StreamingResponse(generate(), media_type="text/event-stream")
