from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, TypedDict


class PatchScopeResult(TypedDict):
    passed: bool
    touched_symbols: list[str]
    allowed_tokens: list[str]
    violations: list[str]
    reason: str


_PY_FUNC_KINDS = (ast.FunctionDef, ast.AsyncFunctionDef)


def validate_patch_scope(
    patch_diff: str,
    *,
    workspace: Path,
    scout_payload: dict[str, Any] | None,
    baseline_payload: dict[str, Any] | None,
) -> PatchScopeResult:
    """Validate that a patch edits code symbols related to the issue target tests.

    This is intentionally heuristic: it is a guardrail, not a proof. It blocks
    obvious scope creep such as a single issue target for invoice totals also
    editing cancellation/date-validation functions. When Scout has no target
    tests, validation is skipped so legacy behavior remains possible.
    """
    target_tests = _target_tests(scout_payload)
    if not target_tests:
        return _result(True, [], [], [], "No target tests; scope validation skipped.")

    touched = _touched_python_symbols(patch_diff, workspace)
    if not touched:
        return _result(True, [], [], [], "No Python symbols touched.")

    allowed_tokens, allowed_symbols = _allowed_scope_tokens(
        target_tests,
        baseline_payload,
        workspace=workspace,
    )
    violations = [
        symbol
        for symbol in touched
        if not _symbol_allowed(symbol, allowed_tokens, allowed_symbols)
    ]
    if violations:
        return _result(
            False,
            touched,
            sorted(allowed_tokens),
            violations,
            "Patch edits symbols that are not supported by the selected target tests.",
        )
    return _result(True, touched, sorted(allowed_tokens), [], "Patch scope matches target tests.")


def _result(
    passed: bool,
    touched_symbols: list[str],
    allowed_tokens: list[str],
    violations: list[str],
    reason: str,
) -> PatchScopeResult:
    return {
        "passed": passed,
        "touched_symbols": sorted(set(touched_symbols)),
        "allowed_tokens": sorted(set(allowed_tokens)),
        "violations": sorted(set(violations)),
        "reason": reason,
    }


def _target_tests(scout_payload: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(scout_payload, dict):
        return []
    raw = scout_payload.get("target_tests")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        dotted = str(item.get("dotted") or "").strip()
        label = str(item.get("label") or "").strip()
        if not dotted and not label:
            continue
        out.append(
            {
                "dotted": dotted,
                "label": label,
                "match_reason": str(item.get("match_reason") or "").strip(),
                "confidence": str(item.get("confidence") or "").strip(),
            }
        )
    return out


def _allowed_scope_tokens(
    target_tests: list[dict[str, str]],
    baseline_payload: dict[str, Any] | None,
    *,
    workspace: Path,
) -> tuple[set[str], set[str]]:
    text_parts: list[str] = []
    for target in target_tests:
        text_parts.extend(
            [
                target.get("dotted", ""),
                target.get("label", ""),
                target.get("match_reason", ""),
            ]
        )
    if isinstance(baseline_payload, dict):
        text_parts.append(str(baseline_payload.get("stderr") or ""))
    tokens = _tokens(" ".join(text_parts))
    symbols = _implementation_symbols_for_targets(
        workspace, target_tests, baseline_payload
    )
    tokens |= _tokens(" ".join(symbols))
    return tokens, symbols


def _implementation_symbols_for_targets(
    workspace: Path,
    target_tests: list[dict[str, str]],
    baseline_payload: dict[str, Any] | None,
) -> set[str]:
    """Map unittest targets to production symbols tied to the failing test context."""
    stems = _module_stems_from_targets(target_tests)
    if not stems:
        return set()

    baseline_text = ""
    if isinstance(baseline_payload, dict):
        baseline_text = str(baseline_payload.get("stderr") or "")

    symbols: set[str] = set()
    for path in workspace.rglob("*.py"):
        rel = path.relative_to(workspace).as_posix()
        if rel.startswith("tests/") or "/tests/" in rel or path.name.startswith("test_"):
            continue
        if path.stem not in stems and not any(stem in path.stem for stem in stems):
            continue
        for func_name in _function_names_in_file(path):
            if any(
                _function_relates_to_target(
                    func_name, target, baseline_text, workspace
                )
                for target in target_tests
            ):
                symbols.add(func_name)
    return symbols


def _resolve_test_file(workspace: Path, dotted: str) -> Path | None:
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        return None
    if parts[0] == "tests" and len(parts) >= 2:
        module = parts[1]
        candidate = workspace / "tests" / f"{module}.py"
        if candidate.exists():
            return candidate
    for index, part in enumerate(parts):
        if part.startswith("test_") and part.endswith(".py") is False:
            candidate = workspace / f"{part}.py"
            if candidate.exists():
                return candidate
            candidate = workspace / "tests" / f"{part}.py"
            if candidate.exists():
                return candidate
    return None


def _function_relates_to_target(
    func_name: str,
    target: dict[str, str],
    baseline_text: str,
    workspace: Path,
) -> bool:
    if func_name in baseline_text:
        return True
    context = " ".join(
        [
            target.get("dotted", ""),
            target.get("label", ""),
            target.get("match_reason", ""),
        ]
    )
    func_tokens = _tokens(func_name)
    context_tokens = _tokens(context)
    if func_tokens & context_tokens:
        return True
    for token in func_tokens:
        if len(token) >= 5 and token in context.lower():
            return True
    test_path = _resolve_test_file(workspace, str(target.get("dotted") or ""))
    if test_path and test_path.exists():
        if func_name in test_path.read_text(encoding="utf-8"):
            return True
    return False


def _module_stems_from_targets(target_tests: list[dict[str, str]]) -> set[str]:
    stems: set[str] = set()
    for target in target_tests:
        dotted = str(target.get("dotted") or "").strip()
        if not dotted:
            continue
        for part in dotted.split("."):
            if part.startswith("test_") and len(part) > 5:
                stems.add(part[5:])
            elif part == "tests":
                continue
            elif part.startswith("Test") and len(part) > 4:
                stems.add(_camel_to_snake(part[4:]))
    return {s for s in stems if len(s) >= 3}


def _camel_to_snake(name: str) -> str:
    if not name:
        return ""
    out: list[str] = []
    chunk: list[str] = []
    for ch in name:
        if ch.isupper() and chunk:
            out.append("".join(chunk).lower())
            chunk = [ch.lower()]
        else:
            chunk.append(ch.lower())
    if chunk:
        out.append("".join(chunk))
    return "_".join(part for part in out if part)


def _function_names_in_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, _PY_FUNC_KINDS):
            names.append(node.name)
    return names


def _symbol_allowed(
    symbol: str,
    allowed_tokens: set[str],
    allowed_symbols: set[str],
) -> bool:
    if symbol in allowed_symbols:
        return True
    symbol_tokens = _tokens(symbol)
    if not symbol_tokens:
        return True
    if symbol_tokens & allowed_tokens:
        return True
    compact_symbol = "".join(sorted(symbol_tokens))
    compact_allowed = {"".join(sorted([token])) for token in allowed_tokens}
    return compact_symbol in compact_allowed


def _tokens(text: str) -> set[str]:
    raw = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text.lower())
    stop = {
        "test",
        "tests",
        "system",
        "hotel",
        "reservation",
        "reservations",
        "assert",
        "self",
        "file",
        "line",
        "reason",
        "issue",
    }
    out: set[str] = set()
    for token in raw:
        for part in token.split("_"):
            if len(part) >= 3 and part not in stop:
                out.add(part)
        if len(token) >= 3 and token not in stop:
            out.add(token)
    return out


def _touched_python_symbols(patch_diff: str, workspace: Path) -> list[str]:
    touched_lines = _changed_new_lines_by_file(patch_diff)
    symbols: list[str] = []
    for rel_path, lines in touched_lines.items():
        if not rel_path.endswith(".py"):
            continue
        file_path = workspace / rel_path
        if not file_path.exists():
            continue
        symbols.extend(_symbols_for_lines(file_path, lines))
    return sorted(set(symbols))


def _changed_new_lines_by_file(patch_diff: str) -> dict[str, set[int]]:
    current_file: str | None = None
    old_line = 0
    new_line = 0
    out: dict[str, set[int]] = {}

    for raw in patch_diff.splitlines():
        if raw.startswith("+++ b/"):
            current_file = raw[len("+++ b/") :].strip()
            out.setdefault(current_file, set())
            continue
        if current_file is None:
            continue
        match = re.match(r"^@@\s+-([0-9]+)(?:,[0-9]+)?\s+\+([0-9]+)(?:,[0-9]+)?", raw)
        if match:
            old_line = int(match.group(1))
            new_line = int(match.group(2))
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if raw.startswith("+"):
            out[current_file].add(new_line)
            new_line += 1
        elif raw.startswith("-"):
            out[current_file].add(max(new_line, 1))
            old_line += 1
        elif raw.startswith(" "):
            old_line += 1
            new_line += 1
    return out


def _symbols_for_lines(file_path: Path, lines: set[int]) -> list[str]:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    funcs: list[tuple[int, int, str]] = []
    for class_node in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
        for child in class_node.body:
            if isinstance(child, _PY_FUNC_KINDS):
                end = getattr(child, "end_lineno", child.lineno)
                funcs.append((child.lineno, int(end), child.name))
    for node in tree.body:
        if isinstance(node, _PY_FUNC_KINDS):
            end = getattr(node, "end_lineno", node.lineno)
            funcs.append((node.lineno, int(end), node.name))

    touched: list[str] = []
    for line in lines:
        matches = [name for start, end, name in funcs if start <= line <= end]
        if matches:
            touched.extend(matches)
    return touched
