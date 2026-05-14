from __future__ import annotations

import json
import re
from typing import Any


def extract_first_json_value(text: str) -> Any | None:
    """Parse the first JSON object or array found in model output."""
    if not text:
        return None
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    fragment = cleaned[start : i + 1]
                    try:
                        return json.loads(fragment)
                    except json.JSONDecodeError:
                        break
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None
