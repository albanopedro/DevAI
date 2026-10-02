"""Check a fix proposal and apply it IN MEMORY, to show a diff (D043).

Nothing here writes to disk. A proposal is rejected whole, with a reason, if
any edit breaks a rule: an edit outside the files the user named, text that
isn't found exactly once, a redaction marker, a new secret, Python or JSON
that would no longer parse, or a change that is too large.
"""

import ast
import difflib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath

from devai.analyzer.testing import is_test_file
from devai.checks.secrets import match_line
from devai.fix.schema import FixProposal

MAX_EDITS = 10
MAX_CHANGED_LINES = 200  # added + removed, over all files
REDACTION_MARKER = "[redacted"


class FixError(Exception):
    """The proposal was rejected; the message is safe to show."""


@dataclass(frozen=True)
class FileChange:
    path: PurePosixPath
    before: str
    after: str
    diff: str  # unified diff, "a/path" → "b/path"


def apply_edits(
    proposal: FixProposal, originals: dict[PurePosixPath, str]
) -> list[FileChange]:
    """The changes `proposal` would make to `originals` (path → current text)."""
    if len(proposal.edits) > MAX_EDITS:
        raise FixError(f"too many edits ({len(proposal.edits)}; at most {MAX_EDITS})")

    contents = dict(originals)
    for number, edit in enumerate(proposal.edits, start=1):
        path = allowed_path(edit.file, originals)
        if path is None:
            raise FixError(
                f"edit {number} changes {edit.file!r}, which wasn't named with --file"
            )
        if REDACTION_MARKER in edit.old_text or REDACTION_MARKER in edit.new_text:
            raise FixError(
                f"edit {number} touches a line hidden as a possible secret in {path}"
            )
        if not edit.old_text:
            raise FixError(f"edit {number} doesn't say which text to replace")

        current = contents[path]
        newline = "\r\n" if "\r\n" in current else "\n"
        old = with_newlines(edit.old_text, newline)
        found = current.count(old)
        if found == 0:
            first = edit.old_text.strip().split("\n")[0][:60]
            raise FixError(f"edit {number}: text not found in {path}: {first!r}")
        if found > 1:
            raise FixError(
                f"edit {number}: the text appears {found} times in {path}; "
                "it must appear exactly once"
            )
        contents[path] = current.replace(old, with_newlines(edit.new_text, newline), 1)

    changes = [
        FileChange(
            path, originals[path], after, unified_diff(path, originals[path], after)
        )
        for path, after in contents.items()
        if after != originals[path]
    ]
    for change in changes:
        check_change(change)

    changed = sum(changed_line_count(change.diff) for change in changes)
    if changed > MAX_CHANGED_LINES:
        raise FixError(
            f"the change is too large ({changed} lines; at most {MAX_CHANGED_LINES})"
        )
    return changes


def allowed_path(
    name: str, originals: dict[PurePosixPath, str]
) -> PurePosixPath | None:
    name = name.strip()
    candidates = [name] + ([name[2:]] if name.startswith("./") else [])
    for candidate in candidates:
        path = PurePosixPath(candidate)
        if path in originals:
            return path
    return None


def with_newlines(text: str, newline: str) -> str:
    """Use the file's own line endings (models write "\\n")."""
    return text.replace("\r\n", "\n").replace("\n", newline)


def check_change(change: FileChange) -> None:
    """Reject a change that adds a secret or breaks the file's syntax."""
    include_generic = not is_test_file(change.path)
    for line in added_lines(change.diff):
        finding = match_line(line, include_generic)
        if finding is not None:
            raise FixError(
                f"the fix would add a possible secret to {change.path} "
                f"({finding.message})"
            )

    suffix = change.path.suffix.lower()
    if suffix == ".py":
        try:
            ast.parse(change.after)
        except SyntaxError as error:
            raise FixError(
                f"the fixed {change.path} would not be valid Python "
                f"(line {error.lineno}: {error.msg})"
            ) from error
    elif suffix == ".json":
        try:
            json.loads(change.after)
        except ValueError as error:
            raise FixError(
                f"the fixed {change.path} would not be valid JSON"
            ) from error


def unified_diff(path: PurePosixPath, before: str, after: str) -> str:
    lines = []
    for line in difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    ):
        if not line.endswith("\n"):
            # A last line without a newline; mark it as git does.
            line += "\n\\ No newline at end of file\n"
        lines.append(line)
    return "".join(lines)


def added_lines(diff: str) -> list[str]:
    return [
        line[1:].rstrip("\r\n")
        for line in diff.splitlines(keepends=True)
        if line.startswith("+") and not line.startswith("+++")
    ]


def changed_line_count(diff: str) -> int:
    return sum(
        1
        for line in diff.splitlines()
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    )
