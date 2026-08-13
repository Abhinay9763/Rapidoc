"""
truth_builder.py — Phase 3, Part D

Combines parsed records + cluster role assignments into a complete truth.json,
saved to templates/uploaded_<hash>.truth.json.

Also includes Part D.5: figure node placeholder support.
"""

import os
import json
import hashlib
import datetime
from collections import Counter
from logger import log


_ALIGNMENT_MAP = {
    "left": "left", "center": "center", "right": "right", "justify": "justify",
}

GENERATABLE_ROLES = {"body_paragraph", "section_heading"}
STATIC_ROLES = {"metadata_field", "static_boilerplate", "caption",
                "reference_entry", "table_header", "table_cell_body", "other"}


def _format_node_id(idx: int, node_type: str) -> str:
    if node_type == "table_cell":
        return f"t_{idx:03d}"
    if node_type == "figure":
        return f"f_{idx:03d}"
    return f"p_{idx:03d}"


def _build_formatting(record: dict) -> dict:
    fmt = record.get("formatting", {})
    return {
        "bold": bool(fmt.get("bold", False)),
        "italic": bool(fmt.get("italic", False)),
        "font": fmt.get("font", "Times New Roman") or "Times New Roman",
        "size_pt": fmt.get("size_pt", 12),
        "underline": bool(fmt.get("underline", False)),
        "alignment": _ALIGNMENT_MAP.get(fmt.get("alignment", "left"), "left"),
    }


def build_truth(
    records: list[dict],
    clusters: list[dict],
    classifications: list[dict],
    output_dir: str,
    source_path: str,
) -> str:
    """
    Build a truth.json from parsed records + classified clusters.

    Returns the path to the written truth.json file.
    """

    # Map each record index → its cluster's classification
    record_to_classification: dict[int, dict] = {}
    for cluster_idx, cluster in enumerate(clusters):
        cls = classifications[cluster_idx]
        for member_id in cluster["member_ids"]:
            record_to_classification[member_id] = cls

    nodes = []
    paragraph_counter = 0
    table_counter = 0
    figure_counter = 0

    current_section: str | None = None
    section_counts: Counter = Counter()
    role_counts: Counter = Counter()
    sections_with_figures: set = set()  # Track which sections already have a figure node

    for rec_idx, record in enumerate(records):
        cls = record_to_classification.get(rec_idx, {"role": "body_paragraph", "confidence": "low", "field_key": None})
        role = cls["role"]
        rec_type = record.get("type", "paragraph")

        # Assign node_id
        if rec_type == "table_cell":
            table_counter += 1
            node_id = _format_node_id(table_counter, "table_cell")
        else:
            paragraph_counter += 1
            node_id = _format_node_id(paragraph_counter, "paragraph")

        # Track current section
        if role == "section_heading":
            current_section = record.get("text", "").strip() or current_section
            section_counts[current_section] += 1

        role_counts[role] += 1

        # Build base node
        node = {
            "node_id": node_id,
            "type": rec_type,
            "role": role,
            "section": current_section,
            "text": record.get("text", ""),
            "formatting": _build_formatting(record),
            "position": record.get("position", {"index": rec_idx}),
            "runs": record.get("runs", []),
        }

        # Metadata field: add field_key
        if role == "metadata_field" and cls.get("field_key"):
            node["field_key"] = cls["field_key"]

        # Table cell: add table_position
        if rec_type == "table_cell" and "table_position" in record:
            node["table_position"] = record["table_position"]

        nodes.append(node)

        # Part D.5: insert a figure placeholder after the FIRST body paragraph per section only.
        # The orchestrator decides whether to actually call diagram_inserter at runtime;
        # this node serves as the integration point marker.
        if (role == "body_paragraph"
                and current_section
                and current_section not in sections_with_figures
                and section_counts.get(current_section, 0) == 1):
            figure_counter += 1
            fig_node = {
                "node_id": _format_node_id(figure_counter, "figure"),
                "type": "figure",
                "role": "figure",
                "section": current_section,
                "caption_node_id": None,
                "generation_spec": None,
                "position": {"index": rec_idx + 1},
            }
            nodes.append(fig_node)
            role_counts["figure"] += 1
            sections_with_figures.add(current_section)

    # Serialize
    truth = {
        "source_template": source_path,
        "nodes": nodes
    }

    # Write to file
    os.makedirs(output_dir, exist_ok=True)
    source_hash = hashlib.md5(source_path.encode()).hexdigest()[:8]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"uploaded_{timestamp}_{source_hash}.truth.json"
    out_path = os.path.join(output_dir, filename)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(truth, f, indent=2, ensure_ascii=False)

    # Log summary
    summary_parts = []
    for role in ["section_heading", "body_paragraph", "metadata_field",
                 "static_boilerplate", "caption", "reference_entry",
                 "table_header", "table_cell_body", "figure", "other"]:
        count = role_counts.get(role, 0)
        if count:
            summary_parts.append(f"{count} {role.replace('_', ' ')}s")

    log.info(f"truth.json written to: {out_path}")
    log.info(f"Summary: {', '.join(summary_parts)}")

    return out_path
