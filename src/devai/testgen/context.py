"""Build the data package an AI test proposal may receive (D046).

Like D042: the chosen source file and the test files that already cover it
(at most MAX_EXISTING_TESTS, to copy their style and imports) are sent whole,
with every line that may hold a secret replaced. Plus the detected test
frameworks and the names `devai test` found no test mentioning.
"""

from typing import Any

from devai.ai.context import build_context
from devai.chat.retrieval import SelectedFile
from devai.checks.secrets import redact_line
from devai.models import CheckReport, ProjectInfo

# Bump when the structure of the context changes.
TESTGEN_CONTEXT_VERSION = 1

MAX_EXISTING_TESTS = 2
MAX_LINES_PER_FILE = 400


def build_testgen_context(
    source: SelectedFile,
    existing_tests: list[SelectedFile],
    untested_names: list[str],
    info: ProjectInfo,
    checks: CheckReport,
) -> dict[str, Any]:
    """Return the JSON-serializable context an AI test proposal may receive."""
    truncated: dict[str, dict[str, int]] = {}
    redacted = 0

    def whole_file(selected: SelectedFile) -> dict[str, str]:
        nonlocal redacted
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
        return {"path": str(selected.path), "content": "\n".join(safe_lines)}

    if len(existing_tests) > MAX_EXISTING_TESTS:
        truncated["existing_tests"] = {
            "shown": MAX_EXISTING_TESTS,
            "total": len(existing_tests),
        }
    return {
        "testgen_context_version": TESTGEN_CONTEXT_VERSION,
        "source": whole_file(source),
        "existing_tests": [
            whole_file(test) for test in existing_tests[:MAX_EXISTING_TESTS]
        ],
        "frameworks": list(info.tests.frameworks),
        "untested_names": list(untested_names),
        "project": build_context(info, checks),  # the allow-listed summary (D025)
        "redacted_lines": redacted,
        "truncated": truncated,
    }
