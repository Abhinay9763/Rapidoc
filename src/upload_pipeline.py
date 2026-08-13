"""
upload_pipeline.py

Orchestrates the full upload path:
  parse_template → build_clusters → classify_clusters → build_truth

Call run_upload_pipeline(template_docx_path) to get back the path to
the generated truth.json file, ready to pass to run_full_generation().
"""

import os
import time
from logger import log
from template_parser import parse_template
from cluster_builder import build_clusters
from role_classifier import classify_clusters
from truth_builder import build_truth


def run_upload_pipeline(template_docx_path: str, output_dir: str) -> str:
    """
    Run the full parse → cluster → classify → build_truth pipeline.

    Returns the path to the generated truth.json.
    Raises on unrecoverable errors (file not found, API failure, etc.)
    """
    t0 = time.time()
    log.info(f"Upload pipeline starting for: {template_docx_path}")

    # Part A: Parse
    records = parse_template(template_docx_path)

    # Part B: Cluster
    clusters = build_clusters(records)

    # Part C: Classify
    classifications = classify_clusters(clusters)

    # Part D: Build truth.json
    truth_path = build_truth(
        records=records,
        clusters=clusters,
        classifications=classifications,
        output_dir=output_dir,
        source_path=template_docx_path,
    )

    elapsed = time.time() - t0
    log.info(f"Upload pipeline complete in {elapsed:.1f}s - {truth_path}")
    return truth_path
