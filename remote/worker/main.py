from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from subprocess import run
from typing import Any

import httpx

_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


def _repo_root() -> Path:
    raw = os.environ.get("MAESTRO_REPO_ROOT", "").strip()
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Repo kökündeki .env (gitignore) — maestro CLI ile aynı KEY=VALUE formatı."""
    path = _repo_root() / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        striped = line.strip()
        if not striped or striped.startswith("#") or "=" not in striped:
            continue
        key, value = striped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name, default)
    return v.strip() if isinstance(v, str) else default


def _parse_maestro_stdout(stdout: str) -> tuple[str | None, str | None]:
    task_id = run_dir = None
    for line in stdout.splitlines():
        if line.startswith("[maestro] task_id="):
            task_id = line.split("=", 1)[1].strip()
        elif line.startswith("[maestro] run_dir="):
            run_dir = line.split("=", 1)[1].strip()
    return task_id, run_dir


def _read_events(run_dir: str | None) -> str | None:
    if not run_dir:
        return None
    path = Path(run_dir) / "events.jsonl"
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def claim(base: str, token: str) -> dict[str, Any] | None:
    r = httpx.post(
        f"{base.rstrip('/')}/worker/claim",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("job")


def finish(
    base: str,
    token: str,
    payload: dict[str, Any],
) -> None:
    r = httpx.post(
        f"{base.rstrip('/')}/worker/finish",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=120.0,
    )
    r.raise_for_status()


def _ensure_git_ref(repo_root: Path) -> None:
    """Optional: MAESTRO_GIT_REF=part2-demo keeps worker on the frozen demo branch."""
    ref = _env("MAESTRO_GIT_REF")
    if not ref:
        return
    proc = run(
        ["git", "checkout", ref],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"git checkout {ref!r} failed: {err}")


def run_maestro(repo: str, issue_ref: str) -> tuple[int, str, str]:
    repo_root = _repo_root()
    if not repo_root.is_dir():
        raise SystemExit(f"MAESTRO_REPO_ROOT is not a directory: {repo_root}")
    _ensure_git_ref(repo_root)
    py = _env("MAESTRO_PYTHON", sys.executable)
    config = _env("MAESTRO_CONFIG", "config.yaml")
    cmd = [py, "-m", "maestro", "run", "--repo", repo, "--issue", issue_ref, "--config", config]
    proc = run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=int(_env("MAESTRO_RUN_TIMEOUT_SECONDS", "7200")),
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def loop() -> None:
    _load_dotenv()
    base = _env("QUEUE_BASE_URL")
    token = _env("WORKER_TOKEN")
    if not base or not token:
        raise SystemExit("Set QUEUE_BASE_URL and WORKER_TOKEN")
    poll = float(_env("WORKER_POLL_SECONDS", "4"))
    print(f"[worker] QUEUE_BASE_URL={base} poll={poll}s", flush=True)
    while True:
        try:
            job = claim(base, token)
        except Exception as e:
            print(f"[worker] claim error: {e}", flush=True)
            time.sleep(poll)
            continue
        if not job:
            time.sleep(poll)
            continue
        jid = job["id"]
        repo = job["repo"]
        issue_ref = job["issue_ref"]
        if not _REPO_RE.match(repo):
            finish(
                base,
                token,
                {
                    "job_id": jid,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "",
                    "error": "invalid repo in job payload",
                },
            )
            continue
        print(f"[worker] running job={jid} repo={repo} issue={issue_ref!r}", flush=True)
        try:
            code, out, err = run_maestro(repo, issue_ref)
        except Exception as e:
            finish(
                base,
                token,
                {
                    "job_id": jid,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": str(e),
                    "error": str(e),
                },
            )
            continue
        tid, rdir = _parse_maestro_stdout(out)
        events = _read_events(rdir)
        finish(
            base,
            token,
            {
                "job_id": jid,
                "exit_code": code,
                "stdout": out,
                "stderr": err,
                "task_id": tid,
                "events_jsonl": events,
                "error": None if code == 0 else f"exit_code={code}",
            },
        )
        print(f"[worker] finished job={jid} exit={code} task_id={tid}", flush=True)


if __name__ == "__main__":
    loop()
