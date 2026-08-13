"""
truth_loader.py

Loads and validates a truth.json file. Works for both the preset path
(handwritten, always has 'formatting') and the upload path (where 'figure'
nodes and some metadata nodes may not have a 'formatting' block).
"""

import json
import os

# Roles that are not required to have a 'formatting' block
_NO_FORMAT_ROLES = {"figure", "metadata_field", "static_boilerplate"}


def load_truth(path: str) -> tuple[list[dict], str | None]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Truth file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes", [])
    source_template = data.get("source_template")

    # Validate required fields on every node
    for node in nodes:
        if "node_id" not in node:
            raise ValueError(f"Missing node_id in node: {node}")
        if "role" not in node:
            raise ValueError(f"Missing role in node: {node}")
        # Only require 'formatting' for roles that need it
        role = node.get("role", "")
        if role not in _NO_FORMAT_ROLES and "formatting" not in node:
            raise ValueError(
                f"Missing 'formatting' in non-figure node {node.get('node_id')!r} "
                f"(role='{role}')"
            )

    return nodes, source_template
