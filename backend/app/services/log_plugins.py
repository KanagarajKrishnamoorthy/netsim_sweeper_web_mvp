from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.models.schemas import OutputMetricCandidate


@dataclass(frozen=True)
class LogMetricDefinition:
    metric_id: str
    group: str
    label: str
    source_file: str
    description: str


LOG_METRIC_DEFS: tuple[LogMetricDefinition, ...] = (
    LogMetricDefinition(
        metric_id="log.packet_trace.total_packets",
        group="Packet Trace",
        label="Total packets",
        source_file="Packet Trace.csv",
        description="Count of rows in Packet Trace.csv",
    ),
    LogMetricDefinition(
        metric_id="log.packet_trace.success_rate",
        group="Packet Trace",
        label="Success rate",
        source_file="Packet Trace.csv",
        description="Successful packets / total packets",
    ),
    LogMetricDefinition(
        metric_id="log.packet_trace.loss_rate",
        group="Packet Trace",
        label="Loss rate",
        source_file="Packet Trace.csv",
        description="(Dropped + Errored) / total packets",
    ),
    LogMetricDefinition(
        metric_id="log.event_trace.total_events",
        group="Event Trace",
        label="Total events",
        source_file="Event Trace.csv",
        description="Count of rows in Event Trace.csv",
    ),
    LogMetricDefinition(
        metric_id="log.event_trace.network_event_share",
        group="Event Trace",
        label="Network event share",
        source_file="Event Trace.csv",
        description="Share of rows where Event_Type is NETWORK",
    ),
    LogMetricDefinition(
        metric_id="log.application.avg_latency_us",
        group="Application Packet Log",
        label="Average latency (us)",
        source_file="Application_Packet_Log.csv",
        description="Mean of Latency(Microseconds)",
    ),
    LogMetricDefinition(
        metric_id="log.application.avg_jitter_us",
        group="Application Packet Log",
        label="Average jitter (us)",
        source_file="Application_Packet_Log.csv",
        description="Mean of Jitter(Microseconds)",
    ),
    LogMetricDefinition(
        metric_id="log.application.goodput_mbps",
        group="Application Packet Log",
        label="Goodput (Mbps)",
        source_file="Application_Packet_Log.csv",
        description="Sum(packet_size_bits)/duration_seconds/1e6",
    ),
    LogMetricDefinition(
        metric_id="log.ltenr.dl_sinr_avg_db",
        group="LTENR Radio Measurements",
        label="DL SINR Avg (dB)",
        source_file="LTENR_Radio_Measurements_Log.csv",
        description="Mean SINR(dB) where Channel=PDSCH",
    ),
    LogMetricDefinition(
        metric_id="log.ltenr.ul_sinr_avg_db",
        group="LTENR Radio Measurements",
        label="UL SINR Avg (dB)",
        source_file="LTENR_Radio_Measurements_Log.csv",
        description="Mean SINR(dB) where Channel=PUSCH",
    ),
)


def _safe_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text in {"NA", "N/A", "-", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _find_file(base: Path, filename: str) -> Path | None:
    candidates = [
        base / filename,
        base / "log" / filename,
        base / "Log" / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def available_log_metric_candidates(scenario_dir: Path) -> list[OutputMetricCandidate]:
    items: list[OutputMetricCandidate] = []
    for definition in LOG_METRIC_DEFS:
        items.append(
            OutputMetricCandidate(
                metric_id=definition.metric_id,
                source_type="log_plugin",
                menu_name=f"Logs::{definition.group}",
                table_name=definition.source_file,
                column_name=definition.label,
                row_key_columns=[],
                source_file=definition.source_file,
                description=definition.description,
                available_now=_find_file(scenario_dir, definition.source_file) is not None,
            )
        )
    return items


def _parse_packet_trace(path: Path) -> dict[str, float | int | None]:
    total = 0
    successful = 0
    dropped = 0
    errored = 0
    with path.open("r", newline="", encoding="latin-1") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        for row in reader:
            total += 1
            status = str(row.get("PACKET_STATUS", "")).strip().lower()
            if status == "successful":
                successful += 1
            elif status == "dropped":
                dropped += 1
            elif status == "errored":
                errored += 1
    return {
        "log.packet_trace.total_packets": total,
        "log.packet_trace.success_rate": (successful / total) if total else None,
        "log.packet_trace.loss_rate": ((dropped + errored) / total) if total else None,
    }


def _parse_event_trace(path: Path) -> dict[str, float | int | None]:
    total = 0
    network = 0
    with path.open("r", newline="", encoding="latin-1") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        for row in reader:
            total += 1
            if str(row.get("Event_Type", "")).strip().lower() == "network":
                network += 1
    return {
        "log.event_trace.total_events": total,
        "log.event_trace.network_event_share": (network / total) if total else None,
    }


def _parse_application_log(path: Path) -> dict[str, float | int | None]:
    latencies: list[float] = []
    jitters: list[float] = []
    min_start: float | None = None
    max_end: float | None = None
    total_bits = 0.0
    with path.open("r", newline="", encoding="latin-1") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        for row in reader:
            latency = _safe_float(row.get("Latency(Microseconds)"))
            jitter = _safe_float(row.get("Jitter(Microseconds)"))
            start_ms = _safe_float(row.get("Packet or Segment Start Time(ms)"))
            end_ms = _safe_float(row.get("Packet or Segment End Time(ms)"))
            size_bytes = _safe_float(row.get("Packet or Segment size(Bytes)"))
            if latency is not None:
                latencies.append(latency)
            if jitter is not None:
                jitters.append(jitter)
            if start_ms is not None:
                min_start = start_ms if min_start is None else min(min_start, start_ms)
            if end_ms is not None:
                max_end = end_ms if max_end is None else max(max_end, end_ms)
            if size_bytes is not None:
                total_bits += size_bytes * 8.0

    duration_s = ((max_end - min_start) / 1000.0) if (min_start is not None and max_end is not None) else None
    goodput = (total_bits / duration_s / 1e6) if duration_s and duration_s > 0 else None

    return {
        "log.application.avg_latency_us": (sum(latencies) / len(latencies)) if latencies else None,
        "log.application.avg_jitter_us": (sum(jitters) / len(jitters)) if jitters else None,
        "log.application.goodput_mbps": goodput,
    }


def _parse_ltenr_radio(path: Path) -> dict[str, float | int | None]:
    dl_sinr: list[float] = []
    ul_sinr: list[float] = []
    with path.open("r", newline="", encoding="latin-1") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        for row in reader:
            channel = str(row.get("Channel", "")).strip().upper()
            sinr = _safe_float(row.get("SINR(dB)"))
            if sinr is None:
                continue
            if channel == "PDSCH":
                dl_sinr.append(sinr)
            elif channel == "PUSCH":
                ul_sinr.append(sinr)
    return {
        "log.ltenr.dl_sinr_avg_db": (sum(dl_sinr) / len(dl_sinr)) if dl_sinr else None,
        "log.ltenr.ul_sinr_avg_db": (sum(ul_sinr) / len(ul_sinr)) if ul_sinr else None,
    }


def extract_log_metrics(run_output_dir: Path) -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {}
    packet_trace = _find_file(run_output_dir, "Packet Trace.csv")
    event_trace = _find_file(run_output_dir, "Event Trace.csv")
    app_log = _find_file(run_output_dir, "Application_Packet_Log.csv")
    ltenr_radio = _find_file(run_output_dir, "LTENR_Radio_Measurements_Log.csv")

    if packet_trace:
        out.update(_parse_packet_trace(packet_trace))
    if event_trace:
        out.update(_parse_event_trace(event_trace))
    if app_log:
        out.update(_parse_application_log(app_log))
    if ltenr_radio:
        out.update(_parse_ltenr_radio(ltenr_radio))
    return out


def log_metric_ids() -> set[str]:
    return {definition.metric_id for definition in LOG_METRIC_DEFS}


def mock_log_metric_value(metric_id: str, run_index: int) -> float:
    token = f"{metric_id}:{run_index}".encode("utf-8")
    digest = hashlib.sha256(token).hexdigest()
    value = int(digest[:8], 16) / 0xFFFFFFFF
    return round(value * 100.0, 5)

