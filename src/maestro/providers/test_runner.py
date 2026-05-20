from __future__ import annotations

import shlex
import subprocess
from pathlib import Path


class TestRunner:
    def __init__(self, repo_path: Path, allowed_prefixes: list[str], timeout_seconds: int = 120) -> None:
        self.repo_path = repo_path
        self.allowed_prefixes = allowed_prefixes
        self.timeout_seconds = timeout_seconds

    def run(self, command: str) -> dict[str, object]:
        if not self._is_allowed(command):
            return {
                "passed": False,
                "exit_code": 126,
                "stdout": "",
                "stderr": f"Command not allowed by whitelist: {command}",
            }
        args = shlex.split(command, posix=False)
        try:
            completed = subprocess.run(
                args,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
            )
            return {
                "passed": completed.returncode == 0,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        except subprocess.TimeoutExpired:
            return {"passed": False, "exit_code": 124, "stdout": "", "stderr": "Test command timed out"}
        except FileNotFoundError:
            return {"passed": False, "exit_code": 127, "stdout": "", "stderr": f"Command not found: {command}"}

    def issue_scoped_commands(self, context: dict[str, object]) -> list[str]:
        """Build test commands scoped to the issue.

        Preference order:
        1. Scout-supplied ``target_test_dotted`` ids → one exact ``unittest <dotted...>`` invocation.
        2. Legacy fallback: derive test files from Scout's ``candidate_files`` + issue tokens.

        The dotted form lets Maestro run only the test(s) the issue actually targets, so
        unrelated red tests stay out of the baseline-vs-post comparison.
        """
        targeted = self._target_dotted_commands(context)
        if targeted:
            return targeted
        return self._legacy_file_scoped_commands(context)

    def _target_dotted_commands(self, context: dict[str, object]) -> list[str]:
        scout = context.get("scout")
        if not isinstance(scout, dict):
            return []
        raw_targets = scout.get("target_test_dotted")
        if not isinstance(raw_targets, list):
            return []
        seen: set[str] = set()
        dotted_ids: list[str] = []
        for entry in raw_targets:
            dotted = str(entry).strip()
            if not dotted or any(ch.isspace() for ch in dotted):
                continue
            if dotted in seen:
                continue
            seen.add(dotted)
            dotted_ids.append(dotted)
            if len(dotted_ids) >= 8:
                break
        if not dotted_ids:
            return []
        # unittest accepts multiple test ids in one command. Keeping target tests
        # together prevents TestVerifier's first-failure selection from shrinking
        # the baseline to a single test.
        return ["python -m unittest " + " ".join(dotted_ids)]

    def _legacy_file_scoped_commands(self, context: dict[str, object]) -> list[str]:
        scout = context.get("scout")
        candidates: list[str] = []
        if isinstance(scout, dict):
            raw = scout.get("candidate_files", [])
            if isinstance(raw, list):
                candidates = [str(x) for x in raw]

        stems: set[str] = set()
        for c in candidates:
            if c.endswith(".py"):
                stems.add(Path(c).stem.lower())

        issue = str(context.get("issue_text", "")).lower()
        for token in issue.replace("/", " ").replace("-", " ").split():
            cleaned = "".join(ch for ch in token if ch.isalnum() or ch == "_")
            if len(cleaned) >= 4:
                stems.add(cleaned)

        cmds: list[str] = []
        seen: set[str] = set()
        for path in sorted(self.repo_path.rglob("test*.py")):
            stem = path.stem.lower()
            if stem in ("test", "tests"):
                continue
            body = stem[5:] if stem.startswith("test_") else stem
            matched = bool(stems) and any(
                s in stem or stem.endswith(s) or body == s or s in body for s in stems
            )
            if not matched:
                continue

            parent = path.parent.relative_to(self.repo_path)
            parent_s = "." if parent == Path(".") else str(parent).replace("\\", "/")
            if parent_s == ".":
                cmd = f"python -m unittest {path.stem}"
            else:
                cmd = f"python -m unittest discover -s {parent_s} -p {path.name}"
            if cmd not in seen:
                seen.add(cmd)
                cmds.append(cmd)
            if len(cmds) >= 8:
                break
        return cmds

    def discover_commands(self) -> list[str]:
        commands: list[str] = [
            "python -m pytest -q",
            "pytest -q",
            "python -m unittest discover -s tests -p test*.py",
            "python -m unittest discover -s . -p test*.py",
        ]
        test_dirs = self._discover_test_dirs(limit=6)
        for test_dir in test_dirs:
            commands.append(f"python -m unittest discover -s {test_dir} -p test*.py")

        # keep order stable while removing duplicates
        seen: set[str] = set()
        unique: list[str] = []
        for cmd in commands:
            if cmd not in seen:
                seen.add(cmd)
                unique.append(cmd)
        return unique

    @staticmethod
    def looks_like_no_tests(result: dict[str, object]) -> bool:
        merged = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
        return ("no tests ran" in merged) or ("ran 0 tests" in merged)

    @staticmethod
    def looks_like_infra_error(result: dict[str, object]) -> bool:
        merged = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
        infra_markers = [
            "no module named pytest",
            "command not allowed by whitelist",
            "command not found",
            "is not recognized as an internal or external command",
            "start directory is not importable",
        ]
        return any(marker in merged for marker in infra_markers)

    def _is_allowed(self, command: str) -> bool:
        normalized = command.strip().lower()
        return any(normalized.startswith(prefix.lower()) for prefix in self.allowed_prefixes)

    def _discover_test_dirs(self, limit: int) -> list[str]:
        dirs: list[str] = []
        for path in self.repo_path.rglob("test*.py"):
            parent = str(path.parent.relative_to(self.repo_path))
            if parent and parent not in dirs:
                dirs.append(parent)
            if len(dirs) >= limit:
                break
        return dirs
