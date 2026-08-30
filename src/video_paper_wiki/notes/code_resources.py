"""Keep only real URLs under ## 代码与资源 on vault paper copies. No network."""

from __future__ import annotations

_HEADING = "代码与资源"


def _kept_url(line: str) -> str | None:
    stripped = line.strip()
    if stripped.endswith("."):
        stripped = stripped[:-1]
    if stripped.startswith("http://") or stripped.startswith("https://"):
        return stripped
    return None


def apply_clean_code_resources(text: str) -> str:
    """Keep http(s) lines under ## 代码与资源. Drop leftover sentences."""
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("##") and line[2:].strip() == _HEADING:
            start = index
            break
    if start is None:
        return text
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("##"):
            end = index
            break
    urls = [url for line in lines[start + 1 : end] if (url := _kept_url(line))]
    mid = [""] + urls + [""] if urls else [""]
    replaced = lines[: start + 1] + mid + lines[end:]
    out = "\n".join(replaced)
    if not out.endswith("\n"):
        out += "\n"
    return out
