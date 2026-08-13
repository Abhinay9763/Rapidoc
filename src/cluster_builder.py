"""
cluster_builder.py — Phase 3, Part B

Groups parsed paragraph/table records by formatting fingerprint so that
role classification (Part C) runs once per cluster instead of once per node.
"""

from logger import log


def _make_fingerprint(record: dict) -> tuple:
    """
    Compute a hashable fingerprint from a record's dominant formatting.
    For multi-span records the dominant formatting was already extracted
    into the top-level `formatting` block by the parser.
    """
    fmt = record.get("formatting", {})
    return (
        record.get("style_name", "Normal"),
        bool(fmt.get("bold", False)),
        bool(fmt.get("italic", False)),
        fmt.get("font", "") or "",
        fmt.get("size_pt"),
        fmt.get("alignment", "left"),
        record.get("type", "paragraph"),  # distinguish table cells from paragraphs
    )


def _position_summary(positions: list[int], total: int) -> str:
    """Produce a human-readable position summary for the LLM prompt."""
    if not positions:
        return "unknown position"
    first = positions[0]
    last = positions[-1]
    spread = last - first
    if len(positions) == 1:
        pct = int(100 * first / max(total, 1))
        return f"appears once at position {first} ({pct}% through document)"
    if spread <= total * 0.1:
        pct = int(100 * first / max(total, 1))
        return f"appears {len(positions)} times, clustered near position {first} ({pct}% through document)"
    return (
        f"appears {len(positions)} times, spread from position {first} to {last} "
        f"(throughout document)"
    )


def _pick_samples(records: list[dict], n: int = 3) -> list[str]:
    """
    Pick n representative text samples from a cluster.
    Prefers short, non-empty texts. Avoids very long paragraphs.
    """
    texts = [r.get("text", "").strip() for r in records if r.get("text", "").strip()]
    if not texts:
        return ["(empty)"]
    # Sort by length ascending, prefer shorter distinctive samples
    texts_sorted = sorted(set(texts), key=len)
    # Take a spread: first, middle, last
    if len(texts_sorted) <= n:
        return texts_sorted[:n]
    indices = [0, len(texts_sorted) // 2, len(texts_sorted) - 1]
    seen = set()
    result = []
    for i in indices:
        t = texts_sorted[i][:200]  # cap at 200 chars for prompt brevity
        if t not in seen:
            result.append(t)
            seen.add(t)
    return result


def build_clusters(records: list[dict]) -> list[dict]:
    """
    Group records by formatting fingerprint and return a list of cluster dicts.

    Each cluster has:
      fingerprint   — the (style, bold, italic, font, size_pt, alignment, type) tuple
      member_ids    — list of record indices (positions in the flat records list)
      count         — number of records in this cluster
      sample_texts  — 2-3 representative text snippets
      position_summary — human-readable spread description
    """
    total = len(records)
    groups: dict[tuple, list[int]] = {}

    for idx, rec in enumerate(records):
        fp = _make_fingerprint(rec)
        groups.setdefault(fp, []).append(idx)

    clusters = []
    for fp, member_ids in groups.items():
        member_records = [records[i] for i in member_ids]
        positions = [records[i].get("position", {}).get("index", i) for i in member_ids]

        clusters.append({
            "fingerprint": fp,
            "member_ids": member_ids,
            "count": len(member_ids),
            "sample_texts": _pick_samples(member_records),
            "position_summary": _position_summary(positions, total),
            "formatting": records[member_ids[0]].get("formatting", {}),
            "style_name": records[member_ids[0]].get("style_name", "Normal"),
            "type": records[member_ids[0]].get("type", "paragraph"),
        })

    # Sort clusters by first occurrence in document for stable ordering
    clusters.sort(key=lambda c: c["member_ids"][0])

    log.info(f"Built {len(clusters)} formatting clusters from {total} records")
    return clusters
