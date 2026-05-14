from __future__ import annotations

from pathlib import Path


def _line_number_prefix(line_no: int) -> str:
    return f"{line_no:>4}| "


def _format_excerpt_with_line_numbers(lines: list[str], *, start_line: int) -> str:
    numbered: list[str] = []
    line_no = start_line
    for line in lines:
        numbered.append(f"{_line_number_prefix(line_no)}{line}")
        line_no += 1
    return "".join(numbered)


def file_excerpt_for_llm(
    repo_path: Path,
    rel: str,
    *,
    head: int = 200,
    tail: int = 40,
    full_if_fewer_than: int = 240,
    include_line_numbers: bool = True,
) -> str | None:
    """Return file body or head/tail window so LLM sees both start and end of long files."""
    p = repo_path / rel
    if not p.is_file():
        return None
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    n = len(lines)
    if n <= full_if_fewer_than:
        if include_line_numbers:
            return _format_excerpt_with_line_numbers(lines, start_line=1)
        return "".join(lines)
    mid_omitted = max(0, n - head - tail)
    head_text = "".join(lines[:head])
    tail_text = "".join(lines[-tail:])
    if include_line_numbers:
        head_text = _format_excerpt_with_line_numbers(lines[:head], start_line=1)
        tail_text = _format_excerpt_with_line_numbers(lines[-tail:], start_line=n - tail + 1)
    return (
        head_text
        + f"\n... ({mid_omitted} lines omitted) ...\n"
        + tail_text
    )
