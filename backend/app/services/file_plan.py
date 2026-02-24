from __future__ import annotations

import fnmatch
from pathlib import Path

from app.models.schemas import FilePlanItem


DEFAULT_OUTPUT_PATTERNS = [
    "Metrics.xml",
    "metrics.xml",
    "result.csv",
    "*Result*.csv",
    "Packet Trace.csv",
    "Event Trace.csv",
    "*.pcap",
    "*.log",
    "*Log*.txt",
    "log/*",
    "log\\*",
    "kpi*.csv",
]


def _matches_any(relative_path: str, patterns: list[str]) -> bool:
    normalized = relative_path.replace("\\", "/")
    return any(
        fnmatch.fnmatch(relative_path, pattern)
        or fnmatch.fnmatch(normalized, pattern.replace("\\", "/"))
        for pattern in patterns
    )


def build_copy_plan(
    scenario_directory: Path,
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> tuple[list[FilePlanItem], list[FilePlanItem]]:
    copy_items: list[FilePlanItem] = []
    excluded_items: list[FilePlanItem] = []
    exclude_set = DEFAULT_OUTPUT_PATTERNS + exclude_patterns

    for file_path in sorted(scenario_directory.rglob("*")):
        if not file_path.is_file():
            continue
        relative = file_path.relative_to(scenario_directory).as_posix()
        size = file_path.stat().st_size
        default_excluded = _matches_any(relative, exclude_set)
        forced_include = _matches_any(relative, include_patterns)

        if default_excluded and not forced_include:
            excluded_items.append(
                FilePlanItem(
                    relative_path=relative,
                    size_bytes=size,
                    classification="output_candidate",
                )
            )
        else:
            copy_items.append(
                FilePlanItem(
                    relative_path=relative,
                    size_bytes=size,
                    classification="input_candidate",
                )
            )

    return copy_items, excluded_items

