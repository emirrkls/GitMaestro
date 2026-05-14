from __future__ import annotations

from pathlib import Path

from maestro.core.score import Score


def count_python_files(workspace: Path) -> int:
    return sum(1 for _ in workspace.rglob("*.py"))


def should_precall_patch_planner(workspace: Path, score: Score) -> bool:
    """Run PatchPlanner proactively for large workspaces or flagged complexity."""
    if score.complexity == "high":
        return True
    return count_python_files(workspace) > 28


def should_spawn_patch_planner_on_surgeon_miss(
    *,
    surgeon_had_material_patch: bool,
    retry_count: int,
    ad_hoc_budget: int,
    ad_hoc_spent: int,
) -> bool:
    if surgeon_had_material_patch or ad_hoc_spent >= ad_hoc_budget:
        return False
    return retry_count >= 1
