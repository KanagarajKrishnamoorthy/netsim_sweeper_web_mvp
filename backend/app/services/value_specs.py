from __future__ import annotations

import csv
import itertools
import math
import random
from pathlib import Path

from app.models.schemas import InputSelection, ValueMode, ValueSpec


def _expand_range(spec: ValueSpec) -> list[str]:
    if spec.start is None or spec.end is None or spec.step in (None, 0):
        raise ValueError("Range mode requires start, end, and non-zero step.")
    if spec.integer_only:
        if not float(spec.start).is_integer() or not float(spec.end).is_integer() or not float(spec.step).is_integer():
            raise ValueError("Range mode with integer_only requires integer start/end/step.")
        start = int(spec.start)
        end = int(spec.end)
        step = int(spec.step)
        if step == 0:
            raise ValueError("Range mode requires non-zero step.")
        values_i: list[str] = []
        current_i = start
        ascending_i = step > 0
        while (current_i <= end) if ascending_i else (current_i >= end):
            values_i.append(str(current_i))
            current_i += step
        return values_i
    values: list[str] = []
    current = spec.start
    ascending = spec.step > 0
    while (current <= spec.end) if ascending else (current >= spec.end):
        values.append(str(current))
        current += spec.step
    return values


def _expand_fixed(spec: ValueSpec) -> list[str]:
    if not spec.values:
        raise ValueError("Fixed mode requires at least one value.")
    return [str(v) for v in spec.values]


def _expand_random(spec: ValueSpec) -> list[str]:
    if spec.minimum is None or spec.maximum is None or spec.count is None:
        raise ValueError("Random mode requires minimum, maximum, and count.")
    if spec.count <= 0:
        raise ValueError("Random mode count must be > 0.")
    seed = spec.seed if spec.seed is not None else 42
    rng = random.Random(seed)
    if spec.integer_only:
        min_i = math.ceil(spec.minimum)
        max_i = math.floor(spec.maximum)
        if min_i > max_i:
            raise ValueError("Random mode integer_only has no integer values in selected range.")
        return [str(rng.randint(min_i, max_i)) for _ in range(spec.count)]
    return [str(rng.uniform(spec.minimum, spec.maximum)) for _ in range(spec.count)]


def _expand_from_file(spec: ValueSpec) -> list[str]:
    if not spec.file_path:
        raise ValueError("from_file mode requires file_path.")
    path = Path(spec.file_path)
    if not path.exists():
        raise ValueError(f"Value file does not exist: {path}")
    values: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if "value" not in (reader.fieldnames or []):
            raise ValueError("Value file must have a 'value' column.")
        for row in reader:
            text = str(row.get("value", "")).strip()
            if text:
                values.append(text)
    if not values:
        raise ValueError("Value file has no usable rows.")
    return values


def expand_value_spec(spec: ValueSpec) -> list[str]:
    if spec.mode == ValueMode.range:
        return _expand_range(spec)
    if spec.mode == ValueMode.fixed:
        return _expand_fixed(spec)
    if spec.mode == ValueMode.random:
        return _expand_random(spec)
    if spec.mode == ValueMode.from_file:
        return _expand_from_file(spec)
    raise ValueError(f"Unsupported mode: {spec.mode}")


def plan_parameter_combinations(
    input_selections: list[InputSelection],
    max_runs: int,
) -> list[dict[str, str]]:
    if not input_selections:
        return [{}]

    key_groups_to_values: list[tuple[list[str], list[str]]] = []
    seen_keys: set[str] = set()
    for selection in input_selections:
        key_group = [selection.parameter_id, *selection.apply_to_parameter_ids]
        dedup_group: list[str] = []
        for key in key_group:
            if key in seen_keys:
                raise ValueError(f"Parameter {key} appears in more than one input selection.")
            if key not in dedup_group:
                dedup_group.append(key)
            seen_keys.add(key)
        values = expand_value_spec(selection.value_spec)
        key_groups_to_values.append((dedup_group, values))

    key_groups = [pair[0] for pair in key_groups_to_values]
    value_lists = [pair[1] for pair in key_groups_to_values]
    combinations = []
    for combo in itertools.product(*value_lists):
        mapping: dict[str, str] = {}
        for key_group, value in zip(key_groups, combo):
            for key in key_group:
                mapping[key] = value
        combinations.append(mapping)
        if len(combinations) > max_runs:
            raise ValueError(
                f"Planned runs exceed limit: {len(combinations)} > {max_runs}. "
                "Reduce parameter ranges or increase max_runs."
            )
    return combinations
