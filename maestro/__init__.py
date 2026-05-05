"""Runtime shim package for src layout local execution."""

from __future__ import annotations

from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_src_pkg = _root / "src" / "maestro"
if _src_pkg.exists():
    __path__.append(str(_src_pkg))  # type: ignore[name-defined]

