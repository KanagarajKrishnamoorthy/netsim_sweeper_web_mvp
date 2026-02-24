from __future__ import annotations

import csv
import random
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from app.models.schemas import (
    InputHierarchyEntity,
    InputHierarchyLayer,
    InputHierarchySection,
    InputParameterCandidate,
    OutputMetricCandidate,
)


NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")
BOOL_VALUES = {"true", "false", "enable", "disable", "yes", "no", "on", "off"}
SECTION_LABEL_MAP: dict[str, str] = {
    "Devices": "Device configuration",
    "Links": "Link configuration",
    "Applications": "Applications configuration",
    "Simulation Parameters": "Simulation parameters",
    "Grid / GUI": "Grid settings",
    "Protocol Configuration": "Protocol configuration",
    "Statistics / Logs": "Statistics and logs",
    "Other": "Other",
}
SECTION_ORDER = [
    "Device configuration",
    "Link configuration",
    "Applications configuration",
    "Simulation parameters",
    "Grid settings",
    "Protocol configuration",
    "Statistics and logs",
    "Other",
]
LAYER_TYPE_MAP = {
    "APPLICATION_LAYER": "Application",
    "TRANSPORT_LAYER": "Transport",
    "NETWORK_LAYER": "Network",
    "DATALINK_LAYER": "Data Link",
    "PHYSICAL_LAYER": "Physical",
}


def find_configuration_files(scenario_folder: Path) -> list[Path]:
    return sorted(scenario_folder.rglob("Configuration.netsim"))


def classify_value_type(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return "empty"
    if text.lower() in BOOL_VALUES:
        return "boolean"
    if NUMERIC_RE.match(text):
        return "number"
    return "string"


def infer_category(ancestor_tags: list[str]) -> str:
    tags = set(ancestor_tags)
    if "CONNECTION" in tags or "LINK" in tags:
        return "Links"
    if "DEVICE_CONFIGURATION" in tags or "DEVICE" in tags:
        return "Devices"
    if "APPLICATION_CONFIGURATION" in tags or "APPLICATION" in tags:
        return "Applications"
    if "SIMULATION_PARAMETER" in tags:
        return "Simulation Parameters"
    if "GUI_INFORMATION" in tags:
        return "Grid / GUI"
    if "STATISTICS_COLLECTION" in tags:
        return "Statistics / Logs"
    if "PROTOCOL_CONFIGURATION" in tags:
        return "Protocol Configuration"
    return "Other"


def _section_label_from_category(category: str) -> str:
    return SECTION_LABEL_MAP.get(category, "Other")


def _to_section_id(section_label: str) -> str:
    return section_label.lower().replace(" ", "_").replace("/", "_")


def _humanize_tag(tag: str) -> str:
    return tag.replace("_", " ").title()


def _find_nearest_tag(
    context: list[tuple[ET.Element, str]],
    tags: set[str],
) -> tuple[ET.Element, str] | None:
    for element, node_path in reversed(context):
        if element.tag in tags:
            return element, node_path
    return None


def _derive_entity(
    section_label: str,
    context: list[tuple[ET.Element, str]],
) -> tuple[str, str, str]:
    if section_label == "Device configuration":
        found = _find_nearest_tag(context, {"DEVICE"})
        if found:
            element, node_path = found
            name = (
                element.attrib.get("DEVICE_NAME")
                or element.attrib.get("KEY")
                or f"Device {element.attrib.get('DEVICE_ID', '').strip()}".strip()
            )
            return node_path or "device_root", name or "Device", "device"
        return "all_devices", "All devices", "device"

    if section_label == "Link configuration":
        found = _find_nearest_tag(context, {"LINK"})
        if found:
            element, node_path = found
            name = element.attrib.get("LINK_NAME") or element.attrib.get("LINK_ID") or "Link"
            return node_path or "link_root", f"Link {name}", "link"
        return "all_links", "All links", "link"

    if section_label == "Applications configuration":
        found = _find_nearest_tag(context, {"APPLICATION"})
        if found:
            element, node_path = found
            name = element.attrib.get("NAME") or element.attrib.get("ID") or "Application"
            return node_path or "application_root", name, "application"
        return "all_applications", "All applications", "application"

    if section_label == "Protocol configuration":
        found = _find_nearest_tag(context, {"PROTOCOL"})
        if found:
            element, node_path = found
            name = element.attrib.get("NAME") or "Protocol"
            return node_path or "protocol_root", name, "protocol"
        return "protocol_global", "Global protocol settings", "global"

    if section_label == "Statistics and logs":
        found = _find_nearest_tag(context, {"PACKET_TRACE", "EVENT_TRACE", "PCAP"})
        if found:
            element, node_path = found
            name = element.attrib.get("NAME") or element.tag
            return node_path or "stats_root", _humanize_tag(name), "log"
        return "stats_global", "Statistics and logs", "global"

    return f"{_to_section_id(section_label)}_global", section_label, "global"


def _derive_layer(
    section_label: str,
    context: list[tuple[ET.Element, str]],
) -> tuple[str, str]:
    tags = [element.tag for element, _ in context]
    nearest_layer = _find_nearest_tag(context, {"LAYER"})
    if section_label == "Device configuration":
        if nearest_layer:
            layer_type = nearest_layer[0].attrib.get("TYPE", "").strip().upper()
            label = LAYER_TYPE_MAP.get(layer_type, _humanize_tag(layer_type or "Layer"))
            return f"layer_{layer_type.lower() or 'generic'}", label
        if "INTERFACE" in tags:
            return "interface", "Interface"
        if "MOBILITY" in tags or "POS_3D" in tags:
            return "mobility", "Mobility"
        return "device_general", "Device"

    if section_label == "Link configuration":
        if "MEDIUM_PROPERTY" in tags:
            return "link_medium", "Medium"
        if tags.count("DEVICE") > 0:
            return "link_endpoints", "Endpoints"
        return "link_general", "Link"

    if section_label == "Applications configuration":
        if "PACKET_SIZE" in tags or "INTER_ARRIVAL_TIME" in tags:
            return "application_traffic", "Traffic"
        return "application_general", "Application"

    if section_label == "Simulation parameters":
        found = _find_nearest_tag(context, {"SEED", "ANIMATION", "INTERACTIVE_SIMULATION"})
        if found:
            return f"simulation_{found[0].tag.lower()}", _humanize_tag(found[0].tag)
        return "simulation_general", "Simulation"

    if section_label == "Grid settings":
        found = _find_nearest_tag(context, {"GUI_INFORMATION"})
        if found:
            return "grid_general", "Grid / GUI"
        return "grid_general", "Grid / GUI"

    if section_label == "Protocol configuration":
        found = _find_nearest_tag(context, {"STATIC_ARP"})
        if found:
            return "protocol_static", _humanize_tag(found[0].tag)
        return "protocol_general", "Protocol"

    if section_label == "Statistics and logs":
        found = _find_nearest_tag(context, {"PACKET_TRACE", "EVENT_TRACE", "PCAP"})
        if found:
            return f"stats_{found[0].tag.lower()}", _humanize_tag(found[0].tag)
        return "stats_general", "Statistics"

    current_tag = context[-1][0].tag if context else "GENERAL"
    return f"other_{current_tag.lower()}", _humanize_tag(current_tag)


def parse_input_parameters(configuration_path: Path) -> list[InputParameterCandidate]:
    tree = ET.parse(configuration_path)
    root = tree.getroot()
    candidates: list[InputParameterCandidate] = []

    def walk(node: ET.Element, idx_path: list[int], ancestors: list[str]) -> None:
        if node.attrib:
            category = infer_category(ancestors + [node.tag])
            for attr_name, current_value in node.attrib.items():
                value_type = classify_value_type(current_value)
                if value_type == "empty":
                    continue
                node_path = ".".join(str(x) for x in idx_path)
                candidate = InputParameterCandidate(
                    parameter_id=f"{node_path}|{attr_name}",
                    category=category,
                    label=f"{node.tag}.{attr_name}",
                    node_path=node_path,
                    attribute_name=attr_name,
                    current_value=str(current_value),
                    value_type=value_type,
                )
                candidates.append(candidate)
        children = list(node)
        for index, child in enumerate(children):
            walk(child, idx_path + [index], ancestors + [node.tag])

    walk(root, [], [])
    return candidates


def parse_input_hierarchy(configuration_path: Path) -> list[InputHierarchySection]:
    tree = ET.parse(configuration_path)
    root = tree.getroot()

    section_bucket: dict[str, dict[str, Any]] = {}

    def ensure_section(section_id: str, section_label: str) -> dict[str, Any]:
        item = section_bucket.get(section_id)
        if item is None:
            item = {
                "section_id": section_id,
                "section_label": section_label,
                "entities": {},
            }
            section_bucket[section_id] = item
        return item

    def ensure_entity(section_obj: dict[str, Any], entity_id: str, entity_label: str, entity_type: str) -> dict[str, Any]:
        entities: dict[str, Any] = section_obj["entities"]
        item = entities.get(entity_id)
        if item is None:
            item = {
                "entity_id": entity_id,
                "entity_label": entity_label,
                "entity_type": entity_type,
                "layers": {},
            }
            entities[entity_id] = item
        return item

    def ensure_layer(entity_obj: dict[str, Any], layer_key: str, layer_label: str) -> dict[str, Any]:
        layers: dict[str, Any] = entity_obj["layers"]
        item = layers.get(layer_key)
        if item is None:
            item = {
                "layer_key": layer_key,
                "layer_label": layer_label,
                "parameters": [],
            }
            layers[layer_key] = item
        return item

    def walk(node: ET.Element, idx_path: list[int], context: list[tuple[ET.Element, str]]) -> None:
        node_path = ".".join(str(x) for x in idx_path)
        current_context = context + [(node, node_path)]
        if node.attrib:
            category = infer_category([item[0].tag for item in current_context])
            section_label = _section_label_from_category(category)
            section_id = _to_section_id(section_label)
            entity_id, entity_label, entity_type = _derive_entity(section_label, current_context)
            layer_key, layer_label = _derive_layer(section_label, current_context)

            section_obj = ensure_section(section_id, section_label)
            entity_obj = ensure_entity(section_obj, entity_id, entity_label, entity_type)
            layer_obj = ensure_layer(entity_obj, layer_key, layer_label)

            for attr_name, current_value in node.attrib.items():
                value_type = classify_value_type(current_value)
                if value_type == "empty":
                    continue
                candidate = InputParameterCandidate(
                    parameter_id=f"{node_path}|{attr_name}",
                    category=category,
                    label=f"{node.tag}.{attr_name}",
                    node_path=node_path,
                    attribute_name=attr_name,
                    current_value=str(current_value),
                    value_type=value_type,
                )
                layer_obj["parameters"].append(candidate)

        for index, child in enumerate(list(node)):
            walk(child, idx_path + [index], current_context)

    walk(root, [], [])

    sections: list[InputHierarchySection] = []
    sorted_section_items = sorted(
        section_bucket.values(),
        key=lambda item: (
            SECTION_ORDER.index(item["section_label"])
            if item["section_label"] in SECTION_ORDER
            else len(SECTION_ORDER),
            item["section_label"],
        ),
    )
    for section_item in sorted_section_items:
        entities: list[InputHierarchyEntity] = []
        for entity_item in section_item["entities"].values():
            layers: list[InputHierarchyLayer] = []
            for layer_item in entity_item["layers"].values():
                layers.append(
                    InputHierarchyLayer(
                        layer_key=layer_item["layer_key"],
                        layer_label=layer_item["layer_label"],
                        parameters=layer_item["parameters"],
                    )
                )
            entities.append(
                InputHierarchyEntity(
                    entity_id=entity_item["entity_id"],
                    entity_label=entity_item["entity_label"],
                    entity_type=entity_item["entity_type"],
                    layers=layers,
                )
            )
        sections.append(
            InputHierarchySection(
                section_id=section_item["section_id"],
                section_label=section_item["section_label"],
                entities=entities,
            )
        )
    return sections


def resolve_node_by_index_path(root: ET.Element, node_path: str) -> ET.Element:
    target = root
    if node_path.strip() == "":
        return target
    for raw_index in node_path.split("."):
        idx = int(raw_index)
        children = list(target)
        target = children[idx]
    return target


def set_parameter_value(
    configuration_path: Path,
    updates: dict[str, str],
    output_path: Path,
) -> None:
    tree = ET.parse(configuration_path)
    root = tree.getroot()
    for parameter_id, value in updates.items():
        node_path, attr_name = parameter_id.split("|", 1)
        node = resolve_node_by_index_path(root, node_path)
        node.set(attr_name, str(value))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def _flatten_th_nodes(th_node: ET.Element, prefix: str = "") -> list[str]:
    current = th_node.attrib.get("name", "").strip()
    child_th = [child for child in list(th_node) if child.tag == "TH"]
    if child_th:
        new_prefix = current if not prefix else f"{prefix}\\{current}" if current else prefix
        columns: list[str] = []
        for child in child_th:
            columns.extend(_flatten_th_nodes(child, new_prefix))
        return columns
    label = current if not prefix else f"{prefix}\\{current}" if current else prefix
    return [label]


def parse_output_metrics(metrics_path: Path) -> list[OutputMetricCandidate]:
    tree = ET.parse(metrics_path)
    root = tree.getroot()
    items: list[OutputMetricCandidate] = []
    for menu in root.findall("MENU"):
        menu_name = menu.attrib.get("Name", "")
        table = menu.find("TABLE")
        if table is None:
            continue
        table_name = table.attrib.get("name", "")
        th_nodes = table.findall("TH")
        flattened: list[str] = []
        for th in th_nodes:
            flattened.extend(_flatten_th_nodes(th))
        row_key_columns = flattened[: min(2, len(flattened))]
        for column in flattened:
            metric_id = f"{menu_name}|{table_name}|{column}"
            items.append(
                OutputMetricCandidate(
                    metric_id=metric_id,
                    menu_name=menu_name,
                    table_name=table_name,
                    column_name=column,
                    row_key_columns=row_key_columns,
                )
            )
    return items


def parse_metrics_value(
    metrics_path: Path,
    metric_id: str,
    row_filters: dict[str, str] | None = None,
) -> str | float | None:
    row_filters = row_filters or {}
    menu_name, table_name, column_name = metric_id.split("|", 2)
    tree = ET.parse(metrics_path)
    root = tree.getroot()
    selected_table: ET.Element | None = None
    for menu in root.findall("MENU"):
        if menu.attrib.get("Name", "") != menu_name:
            continue
        table = menu.find("TABLE")
        if table is None:
            continue
        if table.attrib.get("name", "") == table_name:
            selected_table = table
            break
    if selected_table is None:
        return None

    flattened: list[str] = []
    th_nodes = selected_table.findall("TH")
    for th in th_nodes:
        flattened.extend(_flatten_th_nodes(th))

    if column_name not in flattened:
        return None
    target_index = flattened.index(column_name)

    rows = selected_table.findall("TR")
    if not rows:
        return None

    def row_matches(values: list[str]) -> bool:
        for key, expected in row_filters.items():
            if key not in flattened:
                return False
            idx = flattened.index(key)
            if idx >= len(values):
                return False
            if values[idx] != expected:
                return False
        return True

    selected_values: list[str] | None = None
    for row in rows:
        values = [tc.attrib.get("Value", "") for tc in row.findall("TC")]
        if row_matches(values):
            selected_values = values
            break

    if selected_values is None:
        for row in rows:
            values = [tc.attrib.get("Value", "") for tc in row.findall("TC")]
            if "Link ID" in flattened:
                idx = flattened.index("Link ID")
                if idx < len(values) and values[idx] == "All":
                    selected_values = values
                    break
        if selected_values is None:
            selected_values = [tc.attrib.get("Value", "") for tc in rows[0].findall("TC")]

    if target_index >= len(selected_values):
        return None
    raw = selected_values[target_index]
    if NUMERIC_RE.match(raw.strip()):
        try:
            return float(raw)
        except ValueError:
            return raw
    return raw


def ensure_metrics_file(
    configuration_path: Path,
    provided_metrics_path: Path | None,
) -> tuple[Path | None, list[str]]:
    warnings: list[str] = []
    if provided_metrics_path and provided_metrics_path.exists():
        return provided_metrics_path, warnings
    nearby = configuration_path.parent / "Metrics.xml"
    if nearby.exists():
        warnings.append("Metrics.xml was inferred from the scenario directory.")
        return nearby, warnings
    warnings.append("Metrics.xml not found. Bootstrap run is required to generate it.")
    return None, warnings


def write_value_template_csv(output_file: Path) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["parameter_id", "value"])
        writer.writerow(["0.0|Y_OR_LAT", "10"])
        writer.writerow(["0.0|Y_OR_LAT", "20"])
    return output_file


def create_mock_metrics_file(metrics_out: Path, metric_items: list[OutputMetricCandidate]) -> None:
    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("NetSim_Metrics")
    grouped: dict[tuple[str, str], list[OutputMetricCandidate]] = {}
    for item in metric_items:
        key = (item.menu_name, item.table_name)
        grouped.setdefault(key, []).append(item)

    if not grouped:
        menu = ET.SubElement(root, "MENU", {"Name": "Sweep_Mock"})
        table = ET.SubElement(menu, "TABLE", {"name": "Sweep_Mock"})
        ET.SubElement(table, "TH", {"name": "Run"})
        row = ET.SubElement(table, "TR")
        ET.SubElement(row, "TC", {"Value": "1"})
    else:
        for (menu_name, table_name), items in grouped.items():
            menu = ET.SubElement(root, "MENU", {"Name": menu_name})
            table = ET.SubElement(menu, "TABLE", {"name": table_name})
            for item in items:
                ET.SubElement(table, "TH", {"name": item.column_name})
            row = ET.SubElement(table, "TR")
            for _item in items:
                ET.SubElement(row, "TC", {"Value": f"{random.uniform(1, 100):.6f}"})
    ET.ElementTree(root).write(metrics_out, encoding="utf-8", xml_declaration=True)
