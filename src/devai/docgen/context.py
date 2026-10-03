"""Build the data package a documentation proposal may receive (D049).

Allow-listed, like D025 and D042: the project summary, ONE source file whole
(lines that may hold a secret replaced), and the names in it without docs.
Bounded: at most MAX_LINES_PER_FILE lines and MAX_NAMES names, and only
names whose place is within the lines sent, since the model can't describe
code it doesn't see. Cuts are recorded in "truncated".
"""

from typing import Any

from devai.ai.context import build_context
from devai.analyzer.languages import language_for
from devai.chat.retrieval import SelectedFile
from devai.checks.secrets import redact_line
from devai.docgen.lines import Target
from devai.models import CheckReport, ProjectInfo

# Bump when the structure of the context changes.
DOCS_CONTEXT_VERSION = 1

MAX_LINES_PER_FILE = 400
MAX_NAMES = 20


def build_docs_context(
    source: SelectedFile, targets: list[Target], info: ProjectInfo, checks: CheckReport
) -> dict[str, Any]:
    """Return the JSON-serializable context a documentation proposal may receive."""
    truncated: dict[str, dict[str, int]] = {}
    redacted = 0

    lines = source.text.split("\n")
    if len(lines) > MAX_LINES_PER_FILE:
        truncated["lines"] = {"shown": MAX_LINES_PER_FILE, "total": len(lines)}
        lines = lines[:MAX_LINES_PER_FILE]
    safe_lines = []
    for line in lines:
        safe, was_redacted = redact_line(line.removesuffix("\r"))
        safe_lines.append(safe)
        redacted += was_redacted

    wanted = [target for target in targets if not target.inline]
    visible = [target for target in wanted if target.line < MAX_LINES_PER_FILE]
    names = [target.name for target in visible[:MAX_NAMES]]
    if len(names) < len(wanted):
        truncated["names"] = {"shown": len(names), "total": len(wanted)}

    return {
        "docs_context_version": DOCS_CONTEXT_VERSION,
        "project": build_context(info, checks),  # the allow-listed summary (D025)
        "file": {
            "path": str(source.path),
            "language": language_for(source.path),
            "content": "\n".join(safe_lines),
        },
        "names": names,
        "redacted_lines": redacted,
        "truncated": truncated,
    }
