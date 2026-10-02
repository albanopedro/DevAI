"""Build the data package an AI chat answer may receive (D039).

Third privacy boundary of DevAI, built like D025 and D036:

- Allow-list: the question, the project summary of D025, the selected
  files (chosen locally by retrieval.py or named with --file), and the
  earlier questions and answers of the conversation (D041).
- File lines are numbered, so answers can cite "path:line". Every line that
  may hold a secret is replaced whole, in the files and in the question too.
- Bounded size: at most MAX_CHAT_FILES files, MAX_LINES_PER_FILE lines each,
  MAX_CHAT_CHARACTERS of file content in total, and a capped question. Cuts
  are recorded in "truncated".

Code comes from the project and is untrusted data, never instructions.
"""

from collections.abc import Sequence
from typing import Any

from devai.ai.context import build_context
from devai.chat.retrieval import Selection
from devai.checks.secrets import redact_line
from devai.models import CheckReport, ProjectInfo

# Bump when the structure of the context changes. 2: added "history".
CHAT_CONTEXT_VERSION = 2

MAX_QUESTION_CHARACTERS = 2_000
MAX_CHAT_FILES = 5
MAX_LINES_PER_FILE = 300
MAX_CHAT_CHARACTERS = 30_000
MAX_HISTORY_CHARACTERS = 6_000  # the most recent exchanges are kept


def build_chat_context(
    question: str,
    info: ProjectInfo,
    checks: CheckReport,
    selection: Selection,
    history: Sequence[dict[str, str]] = (),
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

    kept_history, history_redacted = recent_history(history, truncated)
    return {
        "chat_context_version": CHAT_CONTEXT_VERSION,
        "question": "\n".join(safe_question),
        "project": build_context(info, checks),  # the allow-listed summary (D025)
        "files": files,
        "history": kept_history,
        "redacted_lines": redacted + history_redacted,
        "truncated": truncated,
    }


def recent_history(
    history: Sequence[dict[str, str]], truncated: dict[str, dict[str, int]]
) -> tuple[list[dict[str, str]], int]:
    """The latest exchanges that fit MAX_HISTORY_CHARACTERS, oldest first.

    Earlier files are not resent: only questions and answers. They are
    redacted again, in case an answer quoted something it shouldn't have.
    """
    kept: list[dict[str, str]] = []
    redacted = 0
    characters = 0
    for exchange in reversed(history):
        safe = {}
        exchange_redacted = 0
        for key in ("question", "answer"):
            lines = []
            for line in exchange[key].split("\n"):
                text, was_redacted = redact_line(line)
                lines.append(text)
                exchange_redacted += was_redacted
            safe[key] = "\n".join(lines)
        size = len(safe["question"]) + len(safe["answer"])
        if characters + size > MAX_HISTORY_CHARACTERS:
            break
        kept.insert(0, safe)
        characters += size
        redacted += exchange_redacted  # only what is actually sent
    if len(kept) < len(history):
        truncated["history"] = {"shown": len(kept), "total": len(history)}
    return kept, redacted
