"""
diagram_inserter.py — Stub for the Images branch integration point.

The Images branch (teammate) implements the real version of this function.
This stub exists so:
  1. The orchestrator can import it and call it without crashing.
  2. The function signature is fixed and agreed upon.
  3. Merging branches only requires replacing this file's implementation.

Interface contract:
  generate_and_insert_diagram(section_heading, section_content, docx_path) -> bool
    Returns True if a diagram was inserted, False otherwise.
    Must NEVER raise — caller wraps in try/except but stub should be safe too.
"""

from logger import log


def generate_and_insert_diagram(
    section_heading: str,
    section_content: str,
    docx_path: str,
) -> bool:
    """
    Stub: no-op until the Images branch is merged.
    Returns False to signal that no diagram was inserted.
    """
    log.debug(
        f"diagram_inserter: stub called for section '{section_heading}' "
        f"(Images branch not yet merged)"
    )
    return False
