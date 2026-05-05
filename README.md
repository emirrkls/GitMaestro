# GitHub Issue Orchestra (GitMaestro)

GitMaestro is a multi-agent issue resolution orchestrator driven by a central `Maestro` (conductor) instead of a fixed pipeline.

## Current MVP Scope

- Dynamic score generation per issue (`low` / `high` / `ambiguous`)
- Hub-and-spoke messaging (all agent handoffs routed via Maestro)
- Observable message passing with JSONL event logs
- Critic reject -> Surgeon retry loop with escalation on retry exhaustion
- Safety gate before commit readiness
- Ad-hoc runtime agent create/close telemetry
- GitHub integration scaffold (issue fetch + optional branch/commit/push/draft PR)
- Artifact outputs per run under `runs/<task_id>/`

## Core Agents

- `Maestro`: triage, routing, final decision
- `Analyst`: decomposition, hypotheses, repro hints
- `Scout`: code context discovery
- `Surgeon`: minimal patch proposal
- `Critic`: independent review (`approve` / `reject`)
- `Tester`: test command execution and summary evidence
- `Scribe`: commit + PR draft generation

## CLI Usage

```bash
python -m maestro run --repo <owner/name> --issue <id_or_url>
```

Example:

```bash
python -m maestro run --repo octo/demo --issue security-crash-777
```

## Real GitHub Flow Prerequisites

To enable real branch/commit/push/PR operations:

- repository must be a valid git working tree
- `gh` CLI must be installed and authenticated
- runtime flags must be enabled: `allow_commit`, `allow_push`, `allow_pr_draft`

Quick checks:

```bash
git rev-parse --is-inside-work-tree
gh auth status
```

## Configuration

`config.yaml` controls runtime and model routing:

- `models.default` -> default model for non-critic agents
- `models.critic` -> critic model (required: `llama-4-scout`)
- `models.ad_hoc_overrides` -> optional per-agent override map
- `runtime.max_retries` -> critic reject retry limit
- `runtime.ad_hoc_budget` -> max ad-hoc agent usage per issue
- `runtime.test_command_allowlist` -> tester command guardrail
- `runtime.test_timeout_seconds` -> tester timeout
- `runtime.github_enabled` -> use GitHub provider (`gh` CLI based)
- `runtime.allow_pr_draft` -> allow draft PR creation when push is enabled
- `runtime.branch_prefix` -> branch prefix for issue workflows

## Environment Variables

Use `.env` (or `.env.example`) for tokens and toggles:

- `MOCK_LLM=true` for dry-run without external LLM dependency
- `GITHUB_TOKEN`
- `OPENROUTER_API_KEY`
- `GOOGLE_API_KEY`

## Generated Artifacts

Each run writes:

- `runs/<task_id>/events.jsonl`
- `runs/<task_id>/decision_trace.md`
- `runs/<task_id>/patch.diff`
- `runs/<task_id>/test_report.md`
- `runs/<task_id>/pr_draft.md`
- `runs/<task_id>/commit_message.txt`
- `runs/<task_id>/score.json`
- `runs/<task_id>/issue_snapshot.md`
- `runs/<task_id>/github_summary.md`

## Demo Scenarios

Run all 3 required scenarios:

```bash
python scripts/demo_scenarios.py
```

Produces:

- `runs/demo_report.md`

Scenarios:

- simple bug
- complex bug
- ambiguous issue -> human escalation

## Evaluation

Generate evaluation summary from `runs/`:

```bash
python scripts/evaluate_runs.py
```

Produces:

- `EVALUATION_REPORT.md`

Report includes:

- success rate
- retry count
- critic reject accuracy proxy
- false reject proxy
- test pass rate
- estimated duration/cost proxy
- ad-hoc usage frequency and contribution signal

## Notes

- Current implementation is safe-by-default (`allow_commit=false`, `allow_push=false`).
- GitHub integration uses `gh` CLI when available; otherwise it falls back gracefully to synthetic issue metadata.
