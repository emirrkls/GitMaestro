from __future__ import annotations

import argparse
from pathlib import Path

from maestro.config.settings import load_config
from maestro.core.orchestrator import MaestroOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="maestro", description="GitHub Issue Orchestra CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run orchestration for one issue")
    run.add_argument("--repo", required=True, help="GitHub repo in owner/name format")
    run.add_argument("--issue", required=True, help="Issue id or URL")
    run.add_argument("--config", default="config.yaml", help="Config file path")
    run.add_argument("--env-file", default=".env", help="Optional .env path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command != "run":
        return 1

    repo_root = Path.cwd()
    config = load_config(config_path=repo_root / args.config, env_path=repo_root / args.env_file)
    orchestrator = MaestroOrchestrator(repo_path=repo_root, config=config)
    state = orchestrator.run(repo_ref=args.repo, issue_ref=args.issue)
    print(f"[maestro] task_id={state.task_id}")
    print(f"[maestro] run_dir={state.run_dir}")
    print(f"[maestro] complexity={state.score.complexity}")
    print(f"[maestro] model.default={config.models.default}")
    print(f"[maestro] model.critic={config.models.critic}")
    print(f"[maestro] llm.provider={state.context.get('llm_provider', 'unknown')}")
    return 0
