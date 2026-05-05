from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCENARIOS = [
    {"name": "simple_bug", "issue": "bug-12345"},
    {"name": "complex_bug", "issue": "security-crash-777"},
    {"name": "ambiguous_issue", "issue": "12"},
]


def run_cli(repo_root: Path, issue: str) -> dict[str, str]:
    cmd = [sys.executable, "-m", "maestro", "run", "--repo", "octo/demo", "--issue", issue]
    completed = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, shell=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Scenario failed for issue={issue}\n{completed.stderr}")
    output = completed.stdout.strip().splitlines()
    kv: dict[str, str] = {}
    for line in output:
        if "=" in line:
            left, right = line.split("=", 1)
            kv[left.strip()] = right.strip()
    return kv


def load_final_decision(run_dir: Path) -> str:
    events_path = run_dir / "events.jsonl"
    final_decision = "unknown"
    for line in events_path.read_text(encoding="utf-8").splitlines():
        payload = json.loads(line)
        if payload.get("type") == "decision" and payload.get("receiver") == "System":
            final_decision = payload.get("content", {}).get("final_decision", "unknown")
    return final_decision


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    report_lines = ["# Demo Scenarios", ""]
    for scenario in SCENARIOS:
        meta = run_cli(repo_root, scenario["issue"])
        run_dir = Path(meta["[maestro] run_dir"])
        decision = load_final_decision(run_dir)
        report_lines.extend(
            [
                f"## {scenario['name']}",
                f"- issue: `{scenario['issue']}`",
                f"- task_id: `{meta.get('[maestro] task_id', 'n/a')}`",
                f"- complexity: `{meta.get('[maestro] complexity', 'n/a')}`",
                f"- final_decision: `{decision}`",
                f"- run_dir: `{run_dir}`",
                "",
            ]
        )
    out_path = repo_root / "runs" / "demo_report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Demo report generated at: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
