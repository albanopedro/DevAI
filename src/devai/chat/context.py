"""Build the data package an AI chat answer may receive (D039).

Third privacy boundary of DevAI, built like D025 and D036:

- Allow-list: the question, the project summary of D025, and the selected
  files (chosen locally by retrieval.py or named with --file).
- File lines are numbered, so answers can cite "path:line". Every line that
  may hold a secret is replaced whole, in the files and in the question too.
- Bounded size: at most MAX_CHAT_FILES files, MAX_LINES_PER_FILE lines each,
  MAX_CHAT_CHARACTERS of file content in total, and a capped question. Cuts
  are recorded in "truncated".

Code comes from the project and is untrusted data, never instructions.
"""

from typing import Any

from devai.ai.context import build_context
from devai.chat.retrieval import Selection
from devai.checks.secrets import redact_line
from devai.models import CheckReport, ProjectInfo

# Bump when the structure of the context changes.
CHAT_CONTEXT_VERSION = 1

MAX_QUESTION_CHARACTERS = 2_000
MAX_CHAT_FILES = 5
MAX_LINES_PER_FILE = 300
MAX_CHAT_CHARACTERS = 30_000


def build_chat_context(
    question: str, info: ProjectInfo, checks: CheckReport, selection: Selection
) -> dict[str, Any]:
    """Return the JSON-serializable context an AI chat answer may receive."""
    truncated: dict[str, dict[str, int]] = {}
    redacted = 0

    if len(question) > MAX_QUESTION_CHARACTERS:
        truncated["question"] = {
            "shown": MAX_QUESTION_CHARACTERS,
            "total": len(question),
        }
    safe_question = []
    for line in question[:MAX_QUESTION_CHARACTERS].split("\n"):
        safe, was_redacted = redact_line(line)
        safe_question.append(safe)
        redacted += was_redacted

    files = []
    characters = 0
    for selected in selection.files:
        if len(files) == MAX_CHAT_FILES or characters >= MAX_CHAT_CHARACTERS:
            truncated["files"] = {"shown": len(files), "total": len(selection.files)}
            break
        lines = selected.text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()  # a final newline doesn't start another line
        if len(lines) > MAX_LINES_PER_FILE:
            truncated[f"lines:{selected.path}"] = {
                "shown": MAX_LINES_PER_FILE,
                "total": len(lines),
            }
            lines = lines[:MAX_LINES_PER_FILE]
        numbered = []
        for number, line in enumerate(lines, start=1):
            safe, was_redacted = redact_line(line.removesuffix("\r"))
            numbered.append(f"{number}: {safe}")
            redacted += was_redacted
        files.append(
            {"path": str(selected.path), "reason": selected.reason, "lines": numbered}
        )
        characters += sum(len(line) for line in numbered)

    return {
        "chat_context_version": CHAT_CONTEXT_VERSION,
        "question": "\n".join(safe_question),
        "project": build_context(info, checks),  # the allow-listed summary (D025)
        "files": files,
        "redacted_lines": redacted,
        "truncated": truncated,
    }
