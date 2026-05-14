from __future__ import annotations


def is_material_unified_diff(patch: str) -> bool:
    p = patch.strip()
    if not p or p.startswith("# No safe"):
        return False
    lowered = p.lower()
    if lowered.startswith("# planned edits could not be applied"):
        return False
    if "could not be applied safely:" in lowered:
        return False
    return ("@@" in p) or (p.startswith("--- ") and "\n+++ " in p)
