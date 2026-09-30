"""Build the data package an AI code review may receive (D036).

This is the second privacy boundary of DevAI, and the first that includes
code. The same rules as the analysis context (D025), plus:

- Only changed hunks (added and removed lines, with up to 3 lines of
  context) of files the privacy rules allow. Never whole files, never
  unchanged files, never a real .env, lock, minified, binary or large file.
- Every line that matches a secret pattern is replaced, whole, before the
  package is built. Redaction also applies the broad "generic credential"
  rule in test files: hiding a line costs little, sending a secret can't be
  undone.
- Bounded size: at most MAX_DIFF_FILES files with hunks, MAX_LINES_PER_FILE
  lines each, and MAX_DIFF_CHARACTERS in total. Cuts are recorded.

Code and file names come from the reviewed project and are untrusted data,
never instructions.
"""

from typing import Any

from devai.ai.context import cap, finding_context
from devai.checks.secrets import match_line
from devai.models import ChangedFile, CheckReport
from devai.review.diff import Changes, review_diff_lines

# Bump when the structure of the context changes.
REVIEW_CONTEXT_VERSION = 1

MAX_LISTED_FILES = 100
MAX_FINDINGS = 50
MAX_DIFF_FILES = 20
MAX_LINES_PER_FILE = 200
MAX_DIFF_CHARACTERS = 20_000


def build_review_context(changes: Changes, checks: CheckReport) -> dict[str, Any]:
    """Return the JSON-serializable context an AI code review may receive."""
    truncated: dict[str, dict[str, int]] = {}
    diffs, diff_status, redacted = collect_diffs(changes, truncated)

    return {
        "review_context_version": REVIEW_CONTEXT_VERSION,
        "changes": changes.description,
        "files": [
            file_context(file, diff_status[file.path])
            for file in cap(changes.files, MAX_LISTED_FILES, "files", truncated)
        ],
        "findings": [
            finding_context(finding)
            for finding in cap(checks.findings, MAX_FINDINGS, "findings", truncated)
        ],
        "diffs": diffs,
        "redacted_lines": redacted,
        "truncated": truncated,
    }


def collect_diffs(
    changes: Changes, truncated: dict[str, dict[str, int]]
) -> tuple[list[dict[str, Any]], dict[Any, str], int]:
    """Hunks per file within the limits, why other files have none, redactions."""
    diffs: list[dict[str, Any]] = []
    status: dict[Any, str] = {}
    redacted = 0
    characters = 0
    eligible = 0

    for file in changes.files:
        if file.status == "D":
            status[file.path] = "deleted"
            continue
        lines = review_diff_lines(changes, file)
        if lines is None:
            status[file.path] = "not read (privacy or size rules)"
            continue
        if not lines:
            status[file.path] = "no changed lines"
            continue

        eligible += 1
        if len(diffs) == MAX_DIFF_FILES or characters >= MAX_DIFF_CHARACTERS:
            status[file.path] = "not included (size limit)"
            continue

        if len(lines) > MAX_LINES_PER_FILE:
            truncated[f"lines:{file.path}"] = {
                "shown": MAX_LINES_PER_FILE,
                "total": len(lines),
            }
            lines = lines[:MAX_LINES_PER_FILE]
        safe_lines = []
        for line in lines:
            safe, was_redacted = redact(line)
            safe_lines.append(safe)
            redacted += was_redacted
        diffs.append({"path": str(file.path), "lines": safe_lines})
        characters += sum(len(line) for line in safe_lines)
        status[file.path] = "included"

    if eligible > len(diffs):
        truncated["diffs"] = {"shown": len(diffs), "total": eligible}
    return diffs, status, redacted


def redact(line: str) -> tuple[str, bool]:
    """Replace a whole diff line if it may contain a secret. Keeps the +/-/space."""
    marker, text = (line[:1], line[1:]) if line[:1] in "+- " else ("", line)
    finding = match_line(text, include_generic=True)
    if finding is None:
        return line, False
    return f"{marker}[redacted: possible secret ({finding.evidence})]", True


def file_context(file: ChangedFile, diff: str) -> dict[str, Any]:
    return {
        "path": str(file.path),
        "status": file.status,
        "old_path": str(file.old_path) if file.old_path else None,
        "additions": file.additions,
        "deletions": file.deletions,
        "untracked": file.untracked,
        "diff": diff,
    }
