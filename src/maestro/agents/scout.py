from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from maestro.agents.base import AgentResult, BaseAgent
from maestro.agents.json_utils import extract_first_json_value

_TEST_FILE_PATTERNS = ("test_*.py", "*_test.py")
_DEFAULT_TEST_HARVEST_LIMIT = 80
_MAX_DOCSTRING_LEN = 240
_MAX_INLINE_COMMENT_LEN = 240


def _keyword_set(issue: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", issue.lower())
    stop = {"the", "and", "for", "that", "with", "this", "from", "have", "has", "into", "issue"}
    return {t for t in tokens if t not in stop}


def _rank_py_files(repo_path: Path, issue: str, limit: int) -> list[str]:
    keywords = _keyword_set(issue)
    scored: list[tuple[int, str]] = []
    for path in repo_path.rglob("*.py"):
        rel = str(path.relative_to(repo_path)).replace("\\", "/")
        blob = f"{rel} {path.stem.lower()}"
        score = sum(1 for k in keywords if k in blob.lower())
        try:
            size_penalty = 0 if path.stat().st_size < 200_000 else -1
        except OSError:
            size_penalty = -1
        scored.append((score + size_penalty, rel))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored:
        return []
    if scored[0][0] == 0:
        all_rels = sorted(
            str(p.relative_to(repo_path)).replace("\\", "/") for p in repo_path.rglob("*.py")
        )
        return all_rels[:limit]
    return [rel for _, rel in scored[:limit]]


def _module_dotted_path(repo_path: Path, file_path: Path) -> str:
    """Best-effort dotted module path for a test file relative to repo root."""
    rel = file_path.relative_to(repo_path)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts) if parts else file_path.stem


def _first_inline_comment(node: ast.FunctionDef, source_lines: list[str]) -> str:
    """Return the first ``#`` comment between the def header and the end of the function body.

    AST nodes don't carry comments, so we scan the source slice that covers this function
    (and only this function — bounded by ``end_lineno`` to avoid leaking the next test's
    leading comment when bodies are stubs like ``pass``).
    """
    # ``lineno`` is the def line (1-based); start one line past it.
    start = node.lineno  # already 1-based; using as 0-based index yields the line after def
    raw_end = getattr(node, "end_lineno", None)
    if isinstance(raw_end, int) and raw_end > node.lineno:
        end = raw_end
    else:
        end = min(start + 12, len(source_lines))
    end = min(end, len(source_lines))
    for raw in source_lines[start:end]:
        stripped = raw.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:_MAX_INLINE_COMMENT_LEN]
    return ""


def _string_literals(node: ast.FunctionDef) -> str:
    """Collect short string constants from a test body.

    Assertion messages often carry the clearest semantic signal ("extra charges
    leaked", "room is already booked"), while comments/docstrings can be sparse.
    """
    snippets: list[str] = []
    for child in ast.walk(node):
        value: object | None = None
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            value = child.value
        if not isinstance(value, str):
            continue
        text = " ".join(value.split())
        if 4 <= len(text) <= 180 and text not in snippets:
            snippets.append(text)
        if len(snippets) >= 6:
            break
    return " | ".join(snippets)


def _harvest_tests_from_file(
    repo_path: Path,
    file_path: Path,
) -> list[dict[str, str]]:
    """Parse a single test file and emit one record per test function."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    rel = str(file_path.relative_to(repo_path)).replace("\\", "/")
    module_dotted = _module_dotted_path(repo_path, file_path)
    source_lines = source.splitlines()
    records: list[dict[str, str]] = []

    def _emit(func: ast.FunctionDef, class_name: str | None) -> None:
        name = func.name
        if not name.startswith("test"):
            return
        docstring = (ast.get_docstring(func) or "").strip()[:_MAX_DOCSTRING_LEN]
        inline = _first_inline_comment(func, source_lines)
        body_text = _string_literals(func)
        if class_name:
            dotted = f"{module_dotted}.{class_name}.{name}"
            label = f"{name} ({dotted})"
        else:
            dotted = f"{module_dotted}.{name}"
            label = f"{name} ({module_dotted}.py)"
        records.append(
            {
                "file": rel,
                "class": class_name or "",
                "name": name,
                "label": label,
                "dotted": dotted,
                "docstring": docstring,
                "hint": inline,
                "body_text": body_text,
            }
        )

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _emit(child, node.name)  # type: ignore[arg-type]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _emit(node, None)  # type: ignore[arg-type]
    return records


def _harvest_repo_tests(repo_path: Path, limit: int) -> list[dict[str, str]]:
    """Walk the repo for test files and harvest their functions in deterministic order."""
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in _TEST_FILE_PATTERNS:
        for path in sorted(repo_path.rglob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            files.append(path)
    records: list[dict[str, str]] = []
    for path in files:
        records.extend(_harvest_tests_from_file(repo_path, path))
        if len(records) >= limit:
            break
    return records[:limit]


def _score_test_record(record: dict[str, str], keywords: set[str]) -> int:
    """Heuristic relevance score used as fallback / LLM tiebreaker."""
    if not keywords:
        return 0
    blob = " ".join(
        [
            record.get("name", ""),
            record.get("class", ""),
            record.get("docstring", ""),
            record.get("hint", ""),
            record.get("body_text", ""),
            record.get("file", ""),
        ]
    ).lower()
    return sum(1 for k in keywords if k in blob)


def _heuristic_target_selection(
    records: list[dict[str, str]], issue: str
) -> list[dict[str, str]]:
    """Pick the strongest keyword-matching tests when no LLM is available."""
    keywords = _keyword_set(issue)
    scored = [(record, _score_test_record(record, keywords)) for record in records]
    scored.sort(key=lambda item: (-item[1], item[0].get("dotted", "")))
    selected: list[dict[str, str]] = []
    for record, score in scored:
        if score <= 0:
            break
        selected.append(
            {
                "label": record["label"],
                "dotted": record["dotted"],
                "match_reason": f"keyword overlap score={score}",
                "confidence": "low",
            }
        )
        if len(selected) >= 4:
            break
    return selected


def _semantic_target_selection(
    records: list[dict[str, str]],
    issue: str,
    expected_changes: list[str],
) -> list[dict[str, str]]:
    """High-confidence deterministic fallback for common billing/report language.

    This is deliberately narrower than the weak keyword heuristic. It only fires
    when the issue uses financial/billing vocabulary and a test contains strong
    billing/invoice/charge vocabulary, so an explicit empty LLM answer does not
    cause a random target guess.
    """
    issue_tokens = _keyword_set(issue + " " + " ".join(expected_changes))
    billing_issue_terms = {
        "accounting",
        "amount",
        "bill",
        "billing",
        "charge",
        "charges",
        "cost",
        "fee",
        "fees",
        "financial",
        "invoice",
        "paid",
        "payment",
        "report",
        "revenue",
        "total",
    }
    billing_test_terms = {
        "amount",
        "bill",
        "billing",
        "charge",
        "charges",
        "cost",
        "extra",
        "extras",
        "fee",
        "fees",
        "financial",
        "invoice",
        "invoices",
        "leak",
        "leaked",
        "revenue",
        "total",
    }
    if not (issue_tokens & billing_issue_terms):
        return []

    scored: list[tuple[int, dict[str, str], set[str]]] = []
    for record in records:
        blob = " ".join(
            [
                record.get("name", ""),
                record.get("docstring", ""),
                record.get("hint", ""),
                record.get("body_text", ""),
            ]
        )
        record_tokens = _keyword_set(blob)
        matched_terms = record_tokens & billing_test_terms
        score = len(matched_terms)
        if score:
            scored.append((score, record, matched_terms))
    scored.sort(key=lambda item: (-item[0], item[1].get("dotted", "")))
    if not scored:
        return []

    top_score, top_record, matched_terms = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0
    if top_score < 2 or top_score <= second_score:
        return []
    return [
        {
            "label": top_record["label"],
            "dotted": top_record["dotted"],
            "match_reason": (
                "semantic billing/report fallback matched terms: "
                + ", ".join(sorted(matched_terms))
            ),
            "confidence": "medium",
        }
    ]


def _normalize_catalog_test_id(raw: str) -> str:
    """Strip catalog hint suffixes the LLM often copies from the test list.

    The harvest prompt formats rows as ``dotted :: hint``. Models sometimes echo
    ``tests.test_foo.Bar.test_baz :: extra words``; only the dotted id is valid.
    """
    text = raw.strip()
    if " :: " in text:
        text = text.split(" :: ", 1)[0].strip()
    return text


def _validate_llm_target_payload(
    parsed: Any, valid_dotted: set[str], valid_labels: set[str]
) -> tuple[list[dict[str, str]], str]:
    """Sanitize LLM output: drop hallucinated test ids, keep only real ones.

    Returns the cleaned target list plus an optional note for the scout payload.
    """
    if not isinstance(parsed, dict):
        return [], ""
    raw_targets = parsed.get("target_tests")
    if not isinstance(raw_targets, list):
        return [], ""
    cleaned: list[dict[str, str]] = []
    rejected: list[str] = []
    for entry in raw_targets:
        if isinstance(entry, str):
            candidate = entry.strip()
            label = candidate
            dotted = candidate
            reason = ""
            confidence = "medium"
        elif isinstance(entry, dict):
            candidate = str(entry.get("dotted") or entry.get("label") or "").strip()
            label = str(entry.get("label") or candidate).strip()
            dotted = str(entry.get("dotted") or candidate).strip()
            reason = str(entry.get("match_reason") or entry.get("reason") or "").strip()
            confidence = str(entry.get("confidence") or "medium").strip().lower() or "medium"
        else:
            continue

        if not candidate:
            continue

        candidate = _normalize_catalog_test_id(candidate)
        dotted = _normalize_catalog_test_id(dotted)
        label = _normalize_catalog_test_id(label) if label else label

        if dotted in valid_dotted:
            resolved_dotted = dotted
        elif candidate in valid_dotted:
            resolved_dotted = candidate
        else:
            match = next(
                (d for d in valid_dotted if d.endswith("." + candidate) or candidate in d),
                None,
            )
            if match is None:
                match_by_label = next(
                    (lab for lab in valid_labels if candidate in lab or lab in candidate),
                    None,
                )
                if match_by_label is None:
                    rejected.append(candidate)
                    continue
                resolved_dotted = next(
                    (d for d in valid_dotted if d in match_by_label),
                    candidate,
                )
                label = match_by_label
            else:
                resolved_dotted = match

        if not label or label == resolved_dotted:
            label_lookup = next((lab for lab in valid_labels if resolved_dotted in lab), None)
            if label_lookup:
                label = label_lookup
        cleaned.append(
            {
                "label": label or resolved_dotted,
                "dotted": resolved_dotted,
                "match_reason": reason or "LLM selected",
                "confidence": confidence,
            }
        )

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for entry in cleaned:
        key = entry["dotted"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(entry)

    note = ""
    if rejected:
        note = f"Discarded {len(rejected)} unrecognized test id(s) from LLM output."
    return unique, note


def _format_harvest_for_prompt(records: list[dict[str, str]]) -> str:
    """Compact, deterministic representation passed to the LLM."""
    lines: list[str] = []
    for record in records:
        meta = " | ".join(
            part
            for part in (
                record.get("docstring") or "",
                record.get("hint") or "",
                record.get("body_text") or "",
            )
            if part
        )
        meta = meta.replace("\n", " ").strip()
        if meta:
            lines.append(f"- {record['dotted']} :: {meta[:160]}")
        else:
            lines.append(f"- {record['dotted']}")
    return "\n".join(lines)


class CodeExplorerAgent(BaseAgent):
    name = "CodeExplorer"

    def run(self, context: dict[str, object]) -> AgentResult:
        issue = str(context.get("issue_text", ""))
        repo_path = Path(str(context.get("repo_path", ".")))
        candidate_files = _rank_py_files(repo_path, issue, limit=14)
        harvested_tests = _harvest_repo_tests(repo_path, limit=_DEFAULT_TEST_HARVEST_LIMIT)

        analysis_payload = context.get("analysis")
        expected_changes: list[str] = []
        if isinstance(analysis_payload, dict):
            raw_changes = analysis_payload.get("expected_behavior_changes")
            if isinstance(raw_changes, list):
                expected_changes = [str(x).strip() for x in raw_changes if str(x).strip()]

        valid_dotted = {r["dotted"] for r in harvested_tests}
        valid_labels = {r["label"] for r in harvested_tests}

        scout_notes = ""
        target_tests: list[dict[str, str]] = []
        target_selection_source = "none"
        allow_heuristic_fallback = True
        target_selection_blocking = False

        if harvested_tests:
            harvest_block = _format_harvest_for_prompt(harvested_tests)
            intent_block = ""
            if expected_changes:
                intent_block = "Expected behavior changes from IssueAnalyst:\n- " + "\n- ".join(
                    expected_changes[:8]
                )
            prompt = (
                "You are CodeExplorer. Decide which existing tests verify the SINGLE reported "
                "issue. Pick only tests whose name/docstring/hint matches the issue's intent. "
                "Tests for unrelated bugs MUST stay out of the target set even if they happen to "
                "be failing.\n"
                'Return JSON only: {"impact_zones":"short prose", '
                '"target_tests":[{"dotted":"<from list>","label":"<from list>",'
                '"match_reason":"why","confidence":"low|medium|high"}], '
                '"out_of_scope_tests":["<dotted>", "..."]}\n'
                "Rules:\n"
                "- Only choose dotted ids that appear in the catalog below.\n"
                "- Prefer a tight set (1-2 tests). Add more only if the issue clearly spans them.\n"
                "- If unsure, leave target_tests empty so a human can decide.\n\n"
                f"Issue:\n{issue[:2400]}\n\n"
                f"{intent_block}\n\n"
                f"Candidate files (ranked):\n{candidate_files}\n\n"
                f"Test catalog (dotted id :: hint):\n{harvest_block}\n"
            )
            response = self.llm.complete(model=self.model, prompt=prompt)
            scout_notes = response.text
            parsed = extract_first_json_value(response.text)
            target_tests, validation_note = _validate_llm_target_payload(
                parsed, valid_dotted, valid_labels
            )
            if target_tests:
                target_selection_source = "llm"
                allow_heuristic_fallback = False
            elif isinstance(parsed, dict) and isinstance(parsed.get("target_tests"), list):
                semantic_targets = _semantic_target_selection(
                    harvested_tests, issue, expected_changes
                )
                if semantic_targets:
                    target_tests = semantic_targets
                    target_selection_source = "semantic_fallback"
                    allow_heuristic_fallback = False
                    scout_notes = (
                        (scout_notes or "").rstrip()
                        + "\n\n"
                        + "LLM returned no targets; deterministic semantic fallback "
                        + "selected a billing/report test."
                    )
                else:
                    # The model made an explicit "no suitable target" decision.
                    # Respect that signal instead of letting weak keyword matching
                    # pick a random failing test and broaden the patch scope.
                    target_selection_source = "llm_empty"
                    target_selection_blocking = True
                    allow_heuristic_fallback = False
            if validation_note:
                scout_notes = (scout_notes or "").rstrip() + "\n\n" + validation_note
        else:
            prompt = (
                "Given issue text and ranked candidate files, summarize likely impact zones.\n"
                f"Issue: {issue[:2800]}\nFiles: {candidate_files}"
            )
            response = self.llm.complete(model=self.model, prompt=prompt)
            scout_notes = response.text

        if allow_heuristic_fallback and not target_tests and harvested_tests:
            target_tests = _heuristic_target_selection(harvested_tests, issue)
            if target_tests:
                target_selection_source = "heuristic"

        # Provide the dotted id list for downstream agents in a stable shape.
        out_of_scope_tests = sorted(
            r["dotted"] for r in harvested_tests
            if r["dotted"] not in {t["dotted"] for t in target_tests}
        )

        confidence = 0.7
        if target_tests:
            best = max(
                (
                    {"low": 0.6, "medium": 0.72, "high": 0.85}.get(
                        str(t.get("confidence", "")).lower(), 0.65
                    )
                    for t in target_tests
                ),
                default=0.65,
            )
            confidence = best

        return AgentResult(
            summary="Relevant code areas explored with keyword-aware ranking.",
            payload={
                "candidate_files": candidate_files,
                "scout_notes": scout_notes,
                "harvested_tests": harvested_tests,
                "target_tests": target_tests,
                "target_test_labels": [t["label"] for t in target_tests],
                "target_test_dotted": [t["dotted"] for t in target_tests],
                "out_of_scope_tests": out_of_scope_tests,
                "target_selection_source": target_selection_source,
                "target_selection_blocking": target_selection_blocking,
            },
            confidence=confidence,
        )


ScoutAgent = CodeExplorerAgent
