"""Build the data package a fix proposal may receive (D042).

Like D039, with one difference: the named files are sent whole and
unnumbered, so the model can copy the exact text an edit replaces. Lines
that may hold a secret are still replaced, and an edit that touches one is
rejected later (fix/edits.py), because the model never saw that line.
"""

from typing import Any

from devai.ai.context import build_context
from devai.chat.retrieval import SelectedFile
from devai.checks.secrets import redact_line
from devai.models import CheckReport, ProjectInfo

# Bump when the structure of the context changes.
FIX_CONTEXT_VERSION = 1

MAX_FIX_FILES = 3
MAX_LINES_PER_FILE = 400
MAX_REQUEST_CHARACTERS = 2_000


def build_fix_context(
    request: str, info: ProjectInfo, checks: CheckReport, files: list[SelectedFile]
) -> dict[str, Any]:
    """Return the JSON-serializable context a fix proposal may receive."""
    truncated: dict[str, dict[str, int]] = {}
    redacted = 0

    if len(request) > MAX_REQUEST_CHARACTERS:
        truncated["request"] = {"shown": MAX_REQUEST_CHARACTERS, "total": len(request)}
    safe_request = []
    for line in request[:MAX_REQUEST_CHARACTERS].split("\n"):
        safe, was_redacted = redact_line(line)
        safe_request.append(safe)
        redacted += was_redacted

    sent = []
    for selected in files[:MAX_FIX_FILES]:
        lines = selected.text.split("\n")
        if len(lines) > MAX_LINES_PER_FILE:
            truncated[f"lines:{selected.path}"] = {
                "shown": MAX_LINES_PER_FILE,
                "total": len(lines),
            }
            lines = lines[:MAX_LINES_PER_FILE]
        safe_lines = []
        for line in lines:
            safe, was_redacted = redact_line(line.removesuffix("\r"))
            safe_lines.append(safe)
            redacted += was_redacted
        sent.append({"path": str(selected.path), "content": "\n".join(safe_lines)})
    if len(files) > MAX_FIX_FILES:
        truncated["files"] = {"shown": MAX_FIX_FILES, "total": len(files)}

    return {
        "fix_context_version": FIX_CONTEXT_VERSION,
        "request": "\n".join(safe_request),
        "project": build_context(info, checks),  # the allow-listed summary (D025)
        "files": sent,
        "redacted_lines": redacted,
        "truncated": truncated,
    }
