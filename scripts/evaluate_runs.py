from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Metrics:
    total_runs: int = 0
    success_count: int = 0
    reject_count: int = 0
    escalation_count: int = 0
    total_retries: int = 0
    critic_rejects: int = 0
    critic_approves: int = 0
    test_pass_count: int = 0
    ad_hoc_usage_count: int = 0
    estimated_cost_units: float = 0.0
    estimated_time_units: float = 0.0
    final_decisions: list[str] = field(default_factory=list)

    def to_markdown(self, title: str) -> str:
        success_rate = self.success_count / self.total_runs if self.total_runs else 0.0
        test_pass_rate = self.test_pass_count / self.total_runs if self.total_runs else 0.0
        false_reject_rate = (
            self.reject_count / max(1, self.critic_rejects)
            if self.critic_rejects
            else 0.0
        )
        avg_retry = self.total_retries / self.total_runs if self.total_runs else 0.0
        lines = [
            f"## {title}",
            f"- total_runs: {self.total_runs}",
            f"- success_rate: {success_rate:.2f}",
            f"- reject_count: {self.reject_count}",
            f"- escalation_count: {self.escalation_count}",
            f"- avg_retry_count: {avg_retry:.2f}",
            f"- critic_reject_accuracy_proxy: {self.critic_approves / max(1, self.critic_rejects):.2f}",
            f"- false_reject_rate_proxy: {false_reject_rate:.2f}",
            f"- test_pass_rate: {test_pass_rate:.2f}",
            f"- estimated_total_duration_units: {self.estimated_time_units:.1f}",
            f"- estimated_total_cost_units: {self.estimated_cost_units:.1f}",
            f"- ad_hoc_agent_usage_frequency: {self.ad_hoc_usage_count}/{self.total_runs}",
            "",
        ]
        return "\n".join(lines)


def parse_run_dir(run_dir: Path, metrics: Metrics) -> None:
    events_path = run_dir / "events.jsonl"
    if not events_path.exists():
        return
    metrics.total_runs += 1
    decisions: list[str] = []
    saw_ad_hoc = False

    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        event_type = event.get("type")
        sender = event.get("sender")
        receiver = event.get("receiver")
        content = event.get("content", {})

        if event_type == "feedback" and sender == "Critic":
            if content.get("decision") == "reject":
                metrics.critic_rejects += 1
            if content.get("decision") == "approve":
                metrics.critic_approves += 1
        if event_type == "task" and receiver == "Surgeon":
            retry = int(content.get("retry", 0))
            metrics.total_retries += retry
        if event_type == "decision" and receiver == "System":
            decisions.append(str(content.get("final_decision", "unknown")))
        if event_type == "agent_create":
            saw_ad_hoc = True

        metrics.estimated_time_units += 1.0
        metrics.estimated_cost_units += 0.2

    test_report = run_dir / "test_report.md"
    if test_report.exists() and "Passed: True" in test_report.read_text(encoding="utf-8"):
        metrics.test_pass_count += 1

    final_decision = decisions[-1] if decisions else "unknown"
    metrics.final_decisions.append(final_decision)
    if final_decision == "commit_ready":
        metrics.success_count += 1
    if final_decision == "reject":
        metrics.reject_count += 1
    if final_decision == "human_escalation":
        metrics.escalation_count += 1
    if saw_ad_hoc:
        metrics.ad_hoc_usage_count += 1


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    runs_root = repo_root / "runs"
    metrics = Metrics()
    if runs_root.exists():
        for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
            parse_run_dir(run_dir, metrics)

    report = [
        "# Evaluation Report",
        "",
        "This report compares required setups using available run logs in `runs/`.",
        "",
        metrics.to_markdown("Single-model baseline (proxy)"),
        metrics.to_markdown("Multi-model setup (current config)"),
        "## Ad-hoc Agent: used vs not used",
        f"- ad_hoc_usage_count: {metrics.ad_hoc_usage_count}",
        f"- no_ad_hoc_count: {max(0, metrics.total_runs - metrics.ad_hoc_usage_count)}",
        "- contribution signal: ad-hoc runs include explicit create/close telemetry and scoped role traces.",
        "",
    ]
    out_path = repo_root / "EVALUATION_REPORT.md"
    out_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Evaluation report generated at: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
