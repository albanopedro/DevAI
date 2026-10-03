"""Line helpers shared by the Python and JavaScript placement (D049).

The AI writes only text. These helpers clean it, wrap it and insert the
formatted block at a line DevAI chose, keeping the file's line endings.
"""

import re
import textwrap
from dataclasses import dataclass

WIDTH = 79  # passes any linter's default line length
MIN_TEXT_WIDTH = 40  # deep indentation still leaves room for the text

LINE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$")


@dataclass(frozen=True)
class Target:
    """Where the docs for one name go."""

    name: str
    line: int  # 0-based: the docs are inserted right before this line
    indent: str
    inline: bool = False  # Python body on the definition's line: no room for docs
    blank_after: bool = False  # PEP 257: after module and class docstrings


def split_lines(text: str) -> list[str]:
    """Lines with their endings, split only at \\n, \\r\\n and \\r, as Python does.

    str.splitlines() also splits at form feeds and other separators, which
    would shift the line numbers `ast` reports.
    """
    return LINE.findall(text)


def leading_whitespace(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def clean_text(text: str) -> str:
    """Plain lines: no control characters, tabs or trailing spaces, no blank edges.

    Runs of blank lines become one, so paragraphs survive.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    text = "".join(char if char.isprintable() or char == "\n" else " " for char in text)
    kept: list[str] = []
    for line in (line.rstrip() for line in text.split("\n")):
        if line or (kept and kept[-1]):
            kept.append(line)
    while kept and not kept[-1]:
        kept.pop()
    return "\n".join(kept)


def wrap_text(text: str, width: int) -> list[str]:
    """Each line of `text`, wrapped to `width` when longer, keeping its indent.

    Lines the AI broke on purpose (paragraphs, @param tags, list items) stay
    separate; a wrapped tag or list item gets a hanging indent.
    """
    wrapped = []
    for line in text.split("\n"):
        if len(line) <= width:
            wrapped.append(line)
            continue
        lead = leading_whitespace(line)
        hang = lead + ("  " if line.lstrip().startswith(("@", "- ", "* ")) else "")
        wrapped += textwrap.wrap(
            line.strip(),
            width=width,
            initial_indent=lead,
            subsequent_indent=hang,
            break_long_words=False,  # URLs and long names stay whole
            break_on_hyphens=False,
        )
    return wrapped


def insert_blocks(text: str, blocks: list[tuple[Target, list[str]]]) -> str:
    """`text` with each block of lines inserted before its target's line."""
    lines = split_lines(text)
    newline = "\r\n" if "\r\n" in text else "\n"
    for target, block in sorted(blocks, key=lambda item: -item[0].line):
        lines[target.line : target.line] = [line + newline for line in block]
    return "".join(lines)
