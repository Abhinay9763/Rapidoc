"""
role_classifier.py — Phase 3, Part C

Classifies each formatting cluster with a semantic role label using Groq.
One API call per cluster, sequential. Returns a mapping from cluster index
to classification result.
"""

import os
import json
from groq import Groq
from logger import log

VALID_ROLES = {
    "section_heading",
    "body_paragraph",
    "caption",
    "metadata_field",
    "static_boilerplate",
    "table_header",
    "table_cell_body",
    "reference_entry",
    "other",
}

DEFAULT_ROLE = "body_paragraph"

_CLASSIFICATION_SYSTEM = """You are a document structure classifier. You analyze formatting clusters from a .docx template and assign each cluster a semantic role label.

Always respond with valid JSON only — no markdown, no explanation outside the JSON.

Available roles:
- section_heading: major section title (e.g. "1. Introduction", "Methodology")
- body_paragraph: regular paragraph text content
- caption: figure or table caption (short label under an image/table)
- metadata_field: cover page field like student name, roll number, date, institution
- static_boilerplate: fixed text that never changes (e.g. college name, department, "Submitted by")
- table_header: header row of a table
- table_cell_body: data content inside a table cell
- reference_entry: bibliography or reference list item
- other: anything that doesn't fit the above

Response format:
{"role": "<role>", "confidence": "high|medium|low", "field_key": "<optional_key_if_metadata_field>"}

field_key only applies when role is metadata_field. Guess from sample text: student_name, roll_no, date, guide_name, department, institution, title, etc."""


def _build_prompt(cluster: dict) -> str:
    fp = cluster["fingerprint"]
    style_name, bold, italic, font, size_pt, alignment, node_type = fp

    fmt_desc = []
    if bold:
        fmt_desc.append("bold")
    if italic:
        fmt_desc.append("italic")
    if font:
        fmt_desc.append(f"font={font}")
    if size_pt:
        fmt_desc.append(f"size={size_pt}pt")
    fmt_desc.append(f"alignment={alignment}")
    fmt_desc.append(f"Word style='{style_name}'")
    if node_type == "table_cell":
        fmt_desc.append("inside a table")

    samples_str = "\n".join(f"  - \"{s}\"" for s in cluster["sample_texts"])

    return f"""Classify this formatting cluster from a student report template.

Count: {cluster['count']} paragraphs share this exact formatting
Position: {cluster['position_summary']}
Formatting: {', '.join(fmt_desc)}

Sample texts:
{samples_str}

Respond with JSON only."""


def classify_clusters(clusters: list[dict]) -> list[dict]:
    """
    Classify each cluster and return a list of result dicts:
      { "role": str, "confidence": str, "field_key": str|None }

    Index in the returned list matches index in the input clusters list.
    """
    if not os.environ.get("GROQ_API_KEY"):
        raise ValueError("GROQ_API_KEY not set — cannot classify clusters")

    client = Groq()
    results = []

    for i, cluster in enumerate(clusters):
        log.info(f"Classifying cluster {i+1}/{len(clusters)} "
                 f"(count={cluster['count']}, style='{cluster.get('style_name', '')}', "
                 f"samples={cluster['sample_texts'][:1]})")
        try:
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": _CLASSIFICATION_SYSTEM},
                    {"role": "user", "content": _build_prompt(cluster)},
                ],
                model="llama-3.1-8b-instant",
                temperature=0.1,  # low temp for determinism
                max_tokens=128,
            )
            raw = response.choices[0].message.content.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            parsed = json.loads(raw)
            role = parsed.get("role", DEFAULT_ROLE)

            if role not in VALID_ROLES:
                log.warning(f"Cluster {i+1}: unknown role '{role}', defaulting to '{DEFAULT_ROLE}'")
                role = DEFAULT_ROLE

            result = {
                "role": role,
                "confidence": parsed.get("confidence", "low"),
                "field_key": parsed.get("field_key", None) if role == "metadata_field" else None,
            }

            log.info(f"  - role={result['role']} (confidence={result['confidence']})"
                     + (f", field_key={result['field_key']}" if result["field_key"] else ""))

        except Exception as e:
            log.error(f"Cluster {i+1} classification failed: {e}. Defaulting to '{DEFAULT_ROLE}'.")
            result = {"role": DEFAULT_ROLE, "confidence": "low", "field_key": None}

        results.append(result)

    return results
