from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class LicenseMode(str, Enum):
    license_file = "license_file"
    license_server = "license_server"


class ValueMode(str, Enum):
    range = "range"
    fixed = "fixed"
    random = "random"
    from_file = "from_file"


class ExecuteMode(str, Enum):
    dry_run = "dry_run"
    live = "live"


class JobStatus(str, Enum):
    draft = "draft"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class LicenseSpec(BaseModel):
    mode: LicenseMode
    license_file_path: str | None = None
    license_server: str | None = None

    @model_validator(mode="after")
    def validate_mode_fields(self) -> "LicenseSpec":
        if self.mode == LicenseMode.license_file and not self.license_file_path:
            raise ValueError("license_file_path is required when mode=license_file")
        if self.mode == LicenseMode.license_server and not self.license_server:
            raise ValueError("license_server is required when mode=license_server")
        return self


class SessionConfig(BaseModel):
    scenario_folder: str = Field(..., description="Folder containing Configuration.netsim")
    netsim_bin_path: str = Field(..., description="Path to NetSimCore.exe (or bin_x64 folder)")
    output_root: str | None = Field(None, description="Root folder where sweep output is created")
    license: LicenseSpec


class DiscoverConfigurationsRequest(BaseModel):
    scenario_folder: str


class ConfigurationFileItem(BaseModel):
    configuration_path: str
    directory: str
    has_metrics_xml: bool
    has_protocol_logs_config: bool
    has_plot_info: bool
    has_config_support: bool


class DiscoverConfigurationsResponse(BaseModel):
    count: int
    items: list[ConfigurationFileItem]


class InputParameterCandidate(BaseModel):
    parameter_id: str
    category: str
    label: str
    node_path: str
    attribute_name: str
    current_value: str
    value_type: str


class DiscoverInputParametersRequest(BaseModel):
    configuration_path: str


class DiscoverInputParametersResponse(BaseModel):
    configuration_path: str
    count: int
    categories: list[str]
    items: list[InputParameterCandidate]


class DiscoverInputHierarchyRequest(BaseModel):
    configuration_path: str


class InputHierarchyLayer(BaseModel):
    layer_key: str
    layer_label: str
    parameters: list[InputParameterCandidate]


class InputHierarchyEntity(BaseModel):
    entity_id: str
    entity_label: str
    entity_type: str
    layers: list[InputHierarchyLayer]


class InputHierarchySection(BaseModel):
    section_id: str
    section_label: str
    entities: list[InputHierarchyEntity]


class DiscoverInputHierarchyResponse(BaseModel):
    configuration_path: str
    section_count: int
    sections: list[InputHierarchySection]


class OutputMetricCandidate(BaseModel):
    metric_id: str
    source_type: str = "metrics_xml"
    menu_name: str
    table_name: str
    column_name: str
    row_key_columns: list[str] = Field(default_factory=list)
    source_file: str | None = None
    description: str | None = None
    available_now: bool = True


class DiscoverOutputParametersRequest(BaseModel):
    configuration_path: str | None = None
    metrics_path: str | None = None
    generate_metrics_if_missing: bool = False
    bootstrap_session: SessionConfig | None = None
    persist_generated_metrics: bool = False


class DiscoverOutputParametersResponse(BaseModel):
    metrics_path: str | None
    count: int
    menu_names: list[str]
    items: list[OutputMetricCandidate]
    warnings: list[str] = Field(default_factory=list)


class ValueSpec(BaseModel):
    mode: ValueMode
    start: float | None = None
    end: float | None = None
    step: float | None = None
    values: list[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    count: int | None = None
    seed: int | None = None
    file_path: str | None = None
    integer_only: bool = False


class InputSelection(BaseModel):
    parameter_id: str
    label: str
    value_spec: ValueSpec
    apply_to_parameter_ids: list[str] = Field(default_factory=list)


class OutputSelection(BaseModel):
    metric_id: str
    label: str
    source_type: str = "metrics_xml"
    row_filters: dict[str, str] = Field(default_factory=dict)


class FilePlanRequest(BaseModel):
    scenario_directory: str
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)


class FilePlanItem(BaseModel):
    relative_path: str
    size_bytes: int
    classification: str


class FilePlanResponse(BaseModel):
    scenario_directory: str
    include_patterns: list[str]
    exclude_patterns: list[str]
    copy_count: int
    excluded_count: int
    copy_items: list[FilePlanItem]
    excluded_items: list[FilePlanItem]


class SweepJobCreateRequest(BaseModel):
    session: SessionConfig
    configuration_path: str
    metrics_path: str | None = None
    input_parameters: list[InputSelection]
    output_parameters: list[OutputSelection]
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    max_runs: int = 2000
    execute_mode: ExecuteMode = ExecuteMode.dry_run


class PlannedRun(BaseModel):
    run_index: int
    input_values: dict[str, str]
    status: RunStatus = RunStatus.pending
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    artifact_dir: str | None = None
    error_message: str | None = None


class SweepJob(BaseModel):
    job_id: str
    run_name: str | None = None
    created_at: datetime
    status: JobStatus
    session: SessionConfig
    configuration_path: str
    metrics_path: str | None = None
    output_directory: str
    input_parameters: list[InputSelection]
    output_parameters: list[OutputSelection]
    include_patterns: list[str]
    exclude_patterns: list[str]
    execute_mode: ExecuteMode
    planned_run_count: int
    completed_run_count: int = 0
    failed_run_count: int = 0
    cancelled_run_count: int = 0
    result_csv_path: str
    runs: list[PlannedRun]
    warnings: list[str] = Field(default_factory=list)


class JobListResponse(BaseModel):
    jobs: list[SweepJob]


class StartJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class RenameJobRequest(BaseModel):
    run_name: str


class RenameJobResponse(BaseModel):
    job_id: str
    run_name: str
    message: str


class CancelJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class EventMessage(BaseModel):
    event: str
    timestamp: datetime
    payload: dict[str, Any]


class DefaultsResponse(BaseModel):
    default_output_root: str


class SelectFolderRequest(BaseModel):
    title: str | None = None
    initial_path: str | None = None


class SelectFolderResponse(BaseModel):
    path: str | None
    selected: bool
    message: str | None = None


class PathValidationResult(BaseModel):
    path: str
    exists: bool
    valid: bool
    message: str


class ValidateRuntimePathsRequest(BaseModel):
    scenario_folder: str
    netsim_bin_path: str
    output_root: str | None = None


class ValidateRuntimePathsResponse(BaseModel):
    scenario_folder: PathValidationResult
    netsim_bin_path: PathValidationResult
    output_root: PathValidationResult
    all_valid: bool


class ResultCsvResponse(BaseModel):
    headers: list[str]
    rows: list[list[str]]
    total_rows: int


class UiSessionRequest(BaseModel):
    session_id: str


class UiSessionResponse(BaseModel):
    ok: bool
    active_sessions: int
    message: str | None = None
