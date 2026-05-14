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
- `GITHUB_TOKEN` must be set with repo + issues permissions
- runtime flags must be enabled: `allow_commit`, `allow_push`, `allow_pr_draft`

Quick checks:

```bash
git rev-parse --is-inside-work-tree
python -c "import os; print(bool(os.getenv('GITHUB_TOKEN')))"
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
- `runtime.github_enabled` -> use GitHub provider (GitHub REST API based)
- `runtime.allow_pr_draft` -> allow draft PR creation when push is enabled
- `runtime.branch_prefix` -> branch prefix for issue workflows
- `runtime.patch_strategy_*` -> multi-strategy patch controls (`snippet` / `hunk` / `rewrite`) and diff-size thresholds

### Local Ollama and Qwen upgrades

Smaller models (for example `qwen2.5-coder:7b`) are fast but more error-prone on **multi-line Python indentation** and **verbatim `old_snippet` matches**. Upgrading often helps “thinking” quality more than prompt tweaks alone, at the cost of **VRAM, latency, and disk** for the pull.

Practical ladder (pick tags that exist in your `ollama` version; see [Ollama library](https://ollama.com/library)):

| Profile | Typical use | Tradeoff |
|--------|----------------|----------|
| `qwen2.5-coder:7b` | Default in `config.ollama.yaml` | Lowest resource; patch precision weakest |
| `qwen2.5-coder:14b` | Same stack, stronger | More VRAM than 7b |
| `qwen3-coder:latest` / `qwen3-coder:30b` | Stronger coding / agentic behavior | Heavier download and RAM; check Ollama tag page for exact size |
| [`qwen3.5`](https://ollama.com/library/qwen3.5/tags) e.g. `qwen3.5:latest` | Newer general multimodal line (~256K context on Ollama) | Not coder-specialized unless you pick a `*-coding-*` tag |
| `qwen3.5:35b-a3b-coding-nvfp4` (example) | Coding-focused MoE variant on Ollama | Large disk (~22GB class); verify tag sizes on library page |
| [`qwen3.6`](https://ollama.com/library/qwen3.6/tags) e.g. `qwen3.6:27b-coding-nvfp4` | Newer “agentic coding” family per Ollama listing | Heavy; pick quantization to fit GPU RAM |

#### Why we emphasized “coder” models

GitMaestro’s fragile steps are **exact substring edits** (`old_snippet` → `new_snippet`), **Python indentation**, and **structured JSON**. Models trained heavily on code usually fail less on those mechanics than general chat models. That does **not** mean orchestration should ignore reasoning:

- **Orchestration agents** (Maestro triage, Analyst decomposition, Scout narrative) benefit from **strong general / reasoning-oriented** weights — e.g. `qwen3.5:latest` as `models.default`.
- **Patch agents** (Surgeon, PatchPlanner) benefit from **coder-tuned** weights via `ad_hoc_overrides`.

“Thinking” traces ([Ollama thinking capability](https://docs.ollama.com/capabilities/thinking)) can improve deliberation when enabled in Ollama; this repo’s HTTP client currently sends standard chat completions only (no `think` flag). You still get much of the benefit by routing **general models** to planning agents and **coder models** to patch agents.

#### RTX 3060 12GB VRAM + 16GB system RAM (example)

Rough guidance only — always verify with `ollama ps` and your quantization tag:

| Tier | Fits comfortably on 12GB GPU | Risk on 16GB RAM offload |
|------|-------------------------------|----------------------------|
| ~7–9B coder / ~6–7B general Qwen3.5 | Usually full GPU | Low |
| ~14B Q4 coder | Often OK | Medium if extra offload |
| 30B+ / large MoE | Needs partial GPU + CPU offload | **High** — RAM fills fast; swap thrash |

Prefer **`config.ollama.yaml`** hybrid defaults + pull only what you need:

```powershell
.\scripts\ollama_pull_hardware_rtx3060_12gb.ps1
```

**Split routing:** keep `models.default` modest and raise quality only where it hurts most, for example:

```yaml
models:
  default: "qwen3.5:latest"
  critic: "qwen2.5-coder:14b"
  ad_hoc_overrides:
    Surgeon: "qwen2.5-coder:14b"
    PatchPlanner: "qwen2.5-coder:14b"
```

`ad_hoc_overrides` keys are agent names (`PatchPlanner`, `Surgeon`, `Maestro`, `Analyst`, …); unset agents still use `default`.

Also tune `runtime.ollama_max_tokens` if JSON or diffs truncate mid-structure.

For **Ollama thinking** (supported models only — see [Thinking](https://docs.ollama.com/capabilities/thinking)):

```yaml
runtime:
  ollama_think: true          # boolean
  # ollama_think: medium      # or low / medium / high for GPT-OSS-style models
  ollama_timeout_seconds: 720  # per-request HTTP timeout; first model load + think can exceed 3 minutes
```

GitMaestro sends `think` on `/v1/chat/completions`. If the reply leaves `content` empty but fills `reasoning` / `thinking`, the client falls back to that text so JSON parsers still receive a body (verify your Ollama version supports `think` on the OpenAI-compatible route).

If you see **timeouts**, raise `ollama_timeout_seconds`, run `ollama run <your-model>` once to preload weights, or temporarily set `ollama_think: false`.

**Pull models used by `config.ollama.yaml` (RTX 3060 profile):**

```bash
ollama pull qwen3.5:latest
ollama pull qwen2.5-coder:14b
ollama pull qwen2.5-coder:7b
```

Or run `scripts/ollama_pull_hardware_rtx3060_12gb.ps1` / `.sh`.

On Windows, if `ollama` is not on your PATH, the `.ps1` pull scripts resolve `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` automatically (see `scripts/OllamaPath.ps1`).

Pull several suggested Qwen tags locally (disk-heavy; skip tags you do not need):

```powershell
# Windows PowerShell (from repo root)
.\scripts\ollama_pull_qwen.ps1
```

```bash
chmod +x scripts/ollama_pull_qwen.sh && ./scripts/ollama_pull_qwen.sh
```

**Qwen 3.5 / 3.6** (newer families; large downloads — edit the script if you want fewer tags):

```powershell
.\scripts\ollama_pull_qwen_nextgen.ps1
```

```bash
chmod +x scripts/ollama_pull_qwen_nextgen.sh && ./scripts/ollama_pull_qwen_nextgen.sh
```

## Environment Variables

Use `.env` (or `.env.example`) for tokens and toggles. **Do not commit `.env`**; it is listed in `.gitignore`. Copy `.env.example` to `.env` locally and fill in secrets only on your machine.

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
- GitHub integration uses GitHub REST API; if token/permissions are missing, it falls back gracefully and logs the reason in artifacts.
