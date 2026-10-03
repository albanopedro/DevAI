"""Turn the AI's texts into a change that only adds documentation (D049).

Nothing here writes to disk: the result is a FileChange with its diff, which
fix/apply.py writes only after the user's "y" (D044).

An entry for a name DevAI didn't ask about, or a name listed twice or left
empty, is dropped and reported, like the chat's grounding (D040). Anything
unsafe rejects the whole proposal: text that would end the docstring or the
comment (and could slip code in), a redacted line, a possible secret, or a
result that fails the proof that the code is unchanged.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from devai.checks.secrets import match_line
from devai.docgen.js_insert import format_jsdoc, is_one_comment, js_targets
from devai.docgen.lines import Target, clean_text, insert_blocks
from devai.docgen.python_insert import (
    format_docstring,
    python_code_unchanged,
    python_targets,
)
from devai.docmap.js_docs import js_names
from devai.docmap.python_docs import python_names
from devai.fix.edits import FileChange, unified_diff

MAX_DOC_LINES = 20  # text lines of one docstring or comment, after wrapping
REDACTION_MARKER = "[redacted"
JSDOC_LINE_PREFIX = re.compile(r"^\s*\* ?")


class DocsError(Exception):
    """The proposal was rejected whole. The message is safe to show."""


@dataclass(frozen=True)
class DocsPlan:
    change: FileChange | None  # None: nothing to add
    added: tuple[str, ...]
    dropped: tuple[tuple[str, str], ...]  # (name, why)


def find_targets(path: PurePosixPath, text: str) -> list[Target]:
    """Where docs are missing in `text`. Raises NotPython for invalid Python."""
    return python_targets(text) if path.suffix == ".py" else js_targets(text)


def plan_docs(
    path: PurePosixPath,
    text: str,
    docs: Sequence[tuple[str, str]],
    asked: Sequence[str],
) -> DocsPlan:
    """The change that adds `docs` (name, text) for the names DevAI `asked` about."""
    python = path.suffix == ".py"
    targets = {target.name: target for target in find_targets(path, text)}
    blocks: list[tuple[Target, list[str]]] = []
    added: list[str] = []
    dropped: list[tuple[str, str]] = []
    for raw_name, raw_text in docs:
        name = raw_name.strip()
        if name not in asked or name not in targets:
            dropped.append((name, "not one of the names DevAI asked about"))
            continue
        if name in added:
            dropped.append((name, "listed twice; the first text was used"))
            continue
        if targets[name].inline:
            dropped.append((name, "its body is on the definition's line"))
            continue
        body = clean_text(unwrap_markers(raw_text, python))
        check_safe(name, body, python)
        if not body:
            dropped.append((name, "no text"))
            continue

        target = targets[name]
        if python:
            block = format_docstring(body, target.indent)
            if target.blank_after:
                block.append("")
        else:
            block = format_jsdoc(body, target.indent)
        if body.count("\n") + 1 > MAX_DOC_LINES or len(block) > MAX_DOC_LINES + 3:
            dropped.append((name, f"too long (at most {MAX_DOC_LINES} lines)"))
            continue
        blocks.append((target, block))
        added.append(name)

    if not blocks:
        return DocsPlan(None, (), tuple(dropped))
    after = insert_blocks(text, blocks)
    prove_docs_only(path, text, after, blocks, python)
    change = FileChange(path, text, after, unified_diff(path, text, after))
    return DocsPlan(change, tuple(added), tuple(dropped))


def unwrap_markers(text: str, python: bool) -> str:
    """Remove quotes or /** */ the AI put around the text despite the prompt."""
    stripped = text.strip()
    if python:
        for quotes in ('"""', "'''"):
            inner = stripped[3:-3]
            if (
                len(stripped) >= 6
                and stripped.startswith(quotes)
                and stripped.endswith(quotes)
                and quotes not in inner
            ):
                return inner
        return text
    if stripped.startswith("/**") and stripped.endswith("*/"):
        inner = stripped[3:-2]
        if "*/" not in inner:
            lines = inner.split("\n")
            return "\n".join(JSDOC_LINE_PREFIX.sub("", line) for line in lines)
    return text


def check_safe(name: str, body: str, python: bool) -> None:
    """Reject the whole proposal for text that could hide code or a secret."""
    if REDACTION_MARKER in body:
        raise DocsError(
            f"the docs for {name} include a line hidden as a possible secret"
        )
    if python and '"""' in body:
        raise DocsError(
            f'the docs for {name} contain """, which would end the docstring'
        )
    if not python and "*/" in body:
        raise DocsError(f"the docs for {name} contain */, which would end the comment")
    for line in body.split("\n"):
        finding = match_line(line)
        if finding is not None:
            raise DocsError(
                f"the docs for {name} include a possible secret ({finding.message})"
            )


def prove_docs_only(
    path: PurePosixPath,
    before: str,
    after: str,
    blocks: list[tuple[Target, list[str]]],
    python: bool,
) -> None:
    """Fail unless only documentation changed and every name got its docs."""
    names = [target.name for target, _ in blocks]
    if python:
        try:
            unchanged = python_code_unchanged(before, after)
        except SyntaxError:
            raise DocsError(f"the docs would make {path} invalid Python") from None
        if not unchanged:
            raise DocsError(f"the docs would change the code of {path}")
        documented = dict(python_names(after))
    else:
        if not all(is_one_comment(block) for _, block in blocks):
            raise DocsError("a JSDoc block would not be a single comment")
        documented = dict(js_names(after))
    missing = [name for name in names if not documented.get(name)]
    if missing:
        raise DocsError(
            f"the docs for {', '.join(missing)} would not be where docs belong"
        )
