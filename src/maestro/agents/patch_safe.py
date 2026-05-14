from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SnippetEdit:
    path: str
    old_snippet: str
    new_snippet: str


@dataclass(slots=True)
class HunkEdit:
    path: str
    old_block: str
    new_block: str


@dataclass(slots=True)
class RewriteEdit:
    path: str
    new_content: str


@dataclass(slots=True)
class _FuzzyMatchSpan:
    start: int
    end: int


def _normalize_rel(relative: str) -> str:
    return relative.replace("\\", "/").lstrip("/")


def _leading_whitespace(line: str) -> str:
    idx = 0
    while idx < len(line) and line[idx] in (" ", "\t"):
        idx += 1
    return line[:idx]


def _split_lines_no_endings(text: str) -> list[str]:
    return text.splitlines()


def _non_empty_stripped_lines(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]


def _find_fuzzy_match_spans(file_lines: list[str], old_snippet: str) -> list[_FuzzyMatchSpan]:
    old_lines = _split_lines_no_endings(old_snippet)
    old_tokens = _non_empty_stripped_lines(old_lines)
    if not old_tokens:
        return []

    spans: list[_FuzzyMatchSpan] = []
    max_start = len(file_lines)
    for start in range(max_start):
        token_idx = 0
        idx = start
        while idx < len(file_lines):
            stripped = file_lines[idx].strip()
            if not stripped:
                idx += 1
                continue
            if token_idx >= len(old_tokens) or stripped != old_tokens[token_idx]:
                break
            token_idx += 1
            idx += 1
            if token_idx == len(old_tokens):
                spans.append(_FuzzyMatchSpan(start=start, end=idx))
                break
    return spans


def _fuzzy_span_is_safe(old_snippet: str, span: _FuzzyMatchSpan) -> bool:
    old_count = max(1, len(_split_lines_no_endings(old_snippet)))
    matched_count = max(1, span.end - span.start)
    low = old_count * 0.5
    high = old_count * 1.5
    return low <= matched_count <= high


def _file_base_indent_for_span(file_lines: list[str], span: _FuzzyMatchSpan) -> str:
    for line in file_lines[span.start : span.end]:
        if line.strip():
            return _leading_whitespace(line)
    return ""


def _snippet_base_indent(lines: list[str]) -> str:
    for line in lines:
        if line.strip():
            return _leading_whitespace(line)
    return ""


def _reindent_new_snippet(new_snippet: str, target_base_indent: str) -> str:
    line_sep = "\r\n" if "\r\n" in new_snippet else "\n"
    lines = _split_lines_no_endings(new_snippet)
    if not lines:
        return new_snippet
    source_base_indent = _snippet_base_indent(lines)
    rebuilt: list[str] = []
    for line in lines:
        if not line.strip():
            rebuilt.append("")
            continue
        original_indent = _leading_whitespace(line)
        content = line[len(original_indent) :]
        relative_indent = (
            original_indent[len(source_base_indent) :]
            if source_base_indent and original_indent.startswith(source_base_indent)
            else original_indent
        )
        rebuilt.append(f"{target_base_indent}{relative_indent}{content}")
    reindented = line_sep.join(rebuilt)
    if new_snippet.endswith("\n"):
        reindented += line_sep
    return reindented


def _replace_span_with_snippet(buf: str, span: _FuzzyMatchSpan, new_snippet: str) -> str:
    file_lines = buf.splitlines(keepends=True)
    replacement_lines = new_snippet.splitlines(keepends=True)
    out_lines = file_lines[: span.start] + replacement_lines + file_lines[span.end :]
    return "".join(out_lines)


def _apply_single_fuzzy_snippet(buf: str, old_snippet: str, new_snippet: str) -> tuple[bool, str]:
    file_lines = _split_lines_no_endings(buf)
    spans = _find_fuzzy_match_spans(file_lines, old_snippet)
    safe_spans = [span for span in spans if _fuzzy_span_is_safe(old_snippet, span)]
    if not safe_spans:
        return False, buf
    if len(safe_spans) != 1:
        return False, buf
    span = safe_spans[0]
    target_indent = _file_base_indent_for_span(file_lines, span)
    reindented_new = _reindent_new_snippet(new_snippet, target_indent)
    return True, _replace_span_with_snippet(buf, span, reindented_new)


def _find_exact_match_span(buf: str, old_snippet: str) -> _FuzzyMatchSpan | None:
    """Return a line span when ``old_snippet`` appears exactly once in ``buf``."""
    if buf.count(old_snippet) != 1:
        return None
    start_char = buf.find(old_snippet)
    if start_char < 0:
        return None
    end_char = start_char + len(old_snippet)
    start_line = buf[:start_char].count("\n")
    end_line = buf[:end_char].count("\n")
    if end_char > 0 and buf[end_char - 1] != "\n":
        end_line += 1
    if end_line <= start_line:
        end_line = start_line + 1
    return _FuzzyMatchSpan(start=start_line, end=end_line)


def _is_enclosing_block_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped.endswith(":"):
        return False
    return stripped.startswith(("if ", "for ", "while ", "def ", "class ", "with ", "try", "except ", "elif ", "else"))


def _expand_snippet_to_enclosing_block(
    file_lines: list[str],
    span: _FuzzyMatchSpan,
) -> _FuzzyMatchSpan | None:
    """
    Expand a fuzzy-matched span to the nearest enclosing block once.

    The expansion scans upward for the nearest lower-indentation block header, then scans
    downward until the first non-empty line that returns to that header's indentation level
    or less.
    """
    if span.start <= 0 and span.end >= len(file_lines):
        return None
    span_indent_len: int | None = None
    for idx in range(span.start, min(span.end, len(file_lines))):
        if file_lines[idx].strip():
            span_indent_len = len(_leading_whitespace(file_lines[idx]))
            break
    if span_indent_len is None:
        return None

    new_start: int | None = None
    for idx in range(span.start - 1, -1, -1):
        line = file_lines[idx]
        if not line.strip():
            continue
        indent_len = len(_leading_whitespace(line))
        if indent_len < span_indent_len and _is_enclosing_block_header(line):
            new_start = idx
            break
    if new_start is None:
        return None

    block_indent_len = len(_leading_whitespace(file_lines[new_start]))
    new_end = len(file_lines)
    for idx in range(span.end, len(file_lines)):
        line = file_lines[idx]
        if not line.strip():
            continue
        indent_len = len(_leading_whitespace(line))
        if indent_len <= block_indent_len:
            new_end = idx
            break

    expanded = _FuzzyMatchSpan(start=new_start, end=new_end)
    if expanded.start < span.start or expanded.end > span.end:
        return expanded
    return None


def _replace_expanded_span_preserving_context(
    buf: str,
    expanded: _FuzzyMatchSpan,
    matched: _FuzzyMatchSpan,
    replacement: str,
) -> str:
    file_lines = buf.splitlines(keepends=True)
    replacement_lines = replacement.splitlines(keepends=True)
    new_lines = (
        file_lines[: expanded.start]
        + file_lines[expanded.start : matched.start]
        + replacement_lines
        + file_lines[matched.end : expanded.end]
        + file_lines[expanded.end :]
    )
    return "".join(new_lines)


def _python_syntax_error_message_if_expected(path_key: str, before: str, after: str) -> str | None:
    """Only gate .py edits when ``before`` was already valid UTF-8 module syntax."""
    if not path_key.endswith(".py") or before == after:
        return None
    try:
        ast.parse(before, filename=path_key)
    except SyntaxError:
        return None
    try:
        ast.parse(after, filename=path_key)
    except SyntaxError as exc:
        return f"python_syntax_error:{path_key}:line_{exc.lineno}:{exc.msg}"
    return None


def _resolve_under_root(repo_root: Path, relative: str) -> Path | None:
    rel = _normalize_rel(relative)
    if ".." in rel.split("/"):
        return None
    candidate = (repo_root / rel).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        return None
    return candidate


def _build_unified_diff(old_text: str, new_text: str, key: str) -> str:
    return "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{key}",
            tofile=f"b/{key}",
        )
    )


def _batch_finalize(
    initials: dict[str, str],
    current: dict[str, str],
    paths: dict[str, Path],
    *,
    max_diff_lines: int | None = None,
    max_diff_bytes: int | None = None,
) -> tuple[bool, str, list[str], str]:
    for key in current:
        if current[key] == initials[key]:
            continue
        err = _python_syntax_error_message_if_expected(key, initials[key], current[key])
        if err:
            return False, err, [], ""

    diff_parts: list[str] = []
    for key in sorted(current.keys()):
        new_text = current[key]
        old_text = initials[key]
        if new_text == old_text:
            continue
        diff_parts.append(_build_unified_diff(old_text, new_text, key))
    full_diff = "\n".join(diff_parts)
    if max_diff_lines is not None and full_diff.count("\n") > max_diff_lines:
        return False, "diff_lines_too_large", [], ""
    if max_diff_bytes is not None and len(full_diff.encode("utf-8")) > max_diff_bytes:
        return False, "diff_bytes_too_large", [], ""
    for key in sorted(current.keys()):
        if current[key] == initials[key]:
            continue
        paths[key].write_text(current[key], encoding="utf-8")
    touched_sorted = sorted({k for k in current.keys() if current[k] != initials[k]})
    return True, "ok", touched_sorted, full_diff


def apply_snippet_edits(
    repo_root: Path,
    edits: list[SnippetEdit],
    *,
    max_diff_lines: int | None = None,
    max_diff_bytes: int | None = None,
) -> tuple[bool, str, list[str], str]:
    """Validate against in-memory buffers, then write atomically (all-or-nothing per batch)."""
    if not edits:
        return True, "ok", [], ""

    initials: dict[str, str] = {}
    current: dict[str, str] = {}
    paths: dict[str, Path] = {}
    used_fuzzy_match = False
    has_line_count_change = False

    for edit in edits:
        if len(_split_lines_no_endings(edit.old_snippet)) != len(_split_lines_no_endings(edit.new_snippet)):
            has_line_count_change = True
        key = _normalize_rel(edit.path)
        if key not in current:
            path = _resolve_under_root(repo_root, key)
            if path is None or not path.is_file():
                return False, f"invalid_or_missing_file:{key}", [], ""
            text = path.read_text(encoding="utf-8")
            initials[key] = text
            current[key] = text
            paths[key] = path

        buf = current[key]
        count = buf.count(edit.old_snippet)
        if count == 0:
            fuzzy_ok, fuzzy_text = _apply_single_fuzzy_snippet(buf, edit.old_snippet, edit.new_snippet)
            if not fuzzy_ok:
                return False, f"old_snippet_not_found:{key}", [], ""
            current[key] = fuzzy_text
            used_fuzzy_match = True
            continue
        if count != 1:
            return False, f"old_snippet_not_unique:{key}:count={count}", [], ""
        current[key] = buf.replace(edit.old_snippet, edit.new_snippet, 1)

    ok, status, touched, diff = _batch_finalize(
        initials, current, paths, max_diff_lines=max_diff_lines, max_diff_bytes=max_diff_bytes
    )
    if not ok and status.startswith("python_syntax_error:") and has_line_count_change:
        current = dict(initials)
        recovery_ok = False
        for edit in edits:
            key = _normalize_rel(edit.path)
            buf = current.get(key)
            if buf is None:
                recovery_ok = False
                break
            file_lines = _split_lines_no_endings(buf)
            matched = _find_exact_match_span(buf, edit.old_snippet)
            if matched is None:
                spans = _find_fuzzy_match_spans(file_lines, edit.old_snippet)
                safe_spans = [s for s in spans if _fuzzy_span_is_safe(edit.old_snippet, s)]
                if len(safe_spans) != 1:
                    recovery_ok = False
                    break
                matched = safe_spans[0]
            expanded = _expand_snippet_to_enclosing_block(file_lines, matched)
            if expanded is None:
                recovery_ok = False
                break
            target_indent = _file_base_indent_for_span(file_lines, matched)
            reindented_new = _reindent_new_snippet(edit.new_snippet, target_indent)
            current[key] = _replace_expanded_span_preserving_context(
                buf=buf,
                expanded=expanded,
                matched=matched,
                replacement=reindented_new,
            )
            recovery_ok = True
        if recovery_ok:
            ok2, status2, touched2, diff2 = _batch_finalize(
                initials, current, paths, max_diff_lines=max_diff_lines, max_diff_bytes=max_diff_bytes
            )
            if ok2:
                return True, "snippet_fuzzy_block_recovery", touched2, diff2
    if ok and used_fuzzy_match:
        return True, "snippet_fuzzy_match", touched, diff
    return ok, status, touched, diff


def apply_hunk_edits(
    repo_root: Path,
    edits: list[HunkEdit],
    *,
    max_diff_lines: int | None = None,
    max_diff_bytes: int | None = None,
) -> tuple[bool, str, list[str], str]:
    if not edits:
        return True, "ok", [], ""
    initials: dict[str, str] = {}
    current: dict[str, str] = {}
    paths: dict[str, Path] = {}
    for edit in edits:
        key = _normalize_rel(edit.path)
        if key not in current:
            path = _resolve_under_root(repo_root, key)
            if path is None or not path.is_file():
                return False, f"invalid_or_missing_file:{key}", [], ""
            text = path.read_text(encoding="utf-8")
            initials[key] = text
            current[key] = text
            paths[key] = path
        buf = current[key]
        count = buf.count(edit.old_block)
        if count == 0:
            return False, f"hunk_old_block_not_found:{key}", [], ""
        if count != 1:
            return False, f"hunk_old_block_not_unique:{key}:count={count}", [], ""
        current[key] = buf.replace(edit.old_block, edit.new_block, 1)
    return _batch_finalize(
        initials, current, paths, max_diff_lines=max_diff_lines, max_diff_bytes=max_diff_bytes
    )


def apply_rewrite_edits(
    repo_root: Path,
    edits: list[RewriteEdit],
    *,
    max_diff_lines: int | None = None,
    max_diff_bytes: int | None = None,
) -> tuple[bool, str, list[str], str]:
    if not edits:
        return True, "ok", [], ""
    initials: dict[str, str] = {}
    current: dict[str, str] = {}
    paths: dict[str, Path] = {}
    for edit in edits:
        key = _normalize_rel(edit.path)
        path = _resolve_under_root(repo_root, key)
        if path is None or not path.is_file():
            return False, f"invalid_or_missing_file:{key}", [], ""
        text = path.read_text(encoding="utf-8")
        initials[key] = text
        current[key] = edit.new_content
        paths[key] = path
    return _batch_finalize(
        initials, current, paths, max_diff_lines=max_diff_lines, max_diff_bytes=max_diff_bytes
    )


def apply_snippet_edits_safe(
    repo_root: Path,
    edits: list[SnippetEdit],
    *,
    max_new_bytes: int = 50_000,
    max_diff_lines: int = 600,
    max_diff_bytes: int = 100_000,
) -> tuple[bool, str, str, list[str]]:
    growth = sum(len(e.new_snippet) - len(e.old_snippet) for e in edits)
    if growth > max_new_bytes:
        return False, "edit_growth_too_large", "", []
    ok, msg, touched, diff = apply_snippet_edits(
        repo_root, edits, max_diff_lines=max_diff_lines, max_diff_bytes=max_diff_bytes
    )
    if not ok:
        return False, msg, "", touched
    return True, msg, diff, touched


def apply_hunk_edits_safe(
    repo_root: Path,
    edits: list[HunkEdit],
    *,
    max_diff_lines: int = 600,
    max_diff_bytes: int = 100_000,
) -> tuple[bool, str, str, list[str]]:
    ok, msg, touched, diff = apply_hunk_edits(
        repo_root, edits, max_diff_lines=max_diff_lines, max_diff_bytes=max_diff_bytes
    )
    if not ok:
        return False, msg, "", touched
    return True, msg, diff, touched


def apply_rewrite_edits_safe(
    repo_root: Path,
    edits: list[RewriteEdit],
    *,
    rewrite_enabled: bool,
    max_diff_lines: int = 600,
    max_diff_bytes: int = 100_000,
) -> tuple[bool, str, str, list[str]]:
    if not rewrite_enabled:
        return False, "rewrite_disabled", "", []
    ok, msg, touched, diff = apply_rewrite_edits(
        repo_root, edits, max_diff_lines=max_diff_lines, max_diff_bytes=max_diff_bytes
    )
    if not ok:
        return False, msg, "", touched
    return True, msg, diff, touched
