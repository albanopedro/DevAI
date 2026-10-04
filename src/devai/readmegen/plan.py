"""Turn the AI's sections into a README change that only adds text (D050).

Nothing here writes to disk. A section is dropped, with the reason, if its
topic wasn't asked for or is repeated, if its heading doesn't name its topic
(`devai docs` wouldn't find it), if it has a heading of its own level, an
unclosed code block or more than MAX_SECTION_LINES lines, or if a command in
it can't work here: an npm script no package.json has, npm, pnpm or yarn in
a project without package.json (global installs aside), pip, pytest, poetry
or pipenv in a project without Python. `python` and `npx` alone are fine:
`python3 -m http.server` serves any static site. Anything
unsafe rejects the whole proposal: a redacted line, a possible secret, or
HTML that runs code.

New sections go before the license section, or at the end, with the level of
the README's own sections. Then the result is checked: the original lines
are all still there, unchanged and in order, and `devai docs` (D048) run on
the new text finds every added section and no new command that fails.
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from devai.checks.secrets import match_line
from devai.docgen.lines import clean_text
from devai.docmap.readme import (
    FENCE,
    TOPICS,
    WORD,
    matches,
    readme_map,
    script_mentions,
    split_markdown,
)
from devai.fix.edits import FileChange, unified_diff
from devai.readmegen.context import ProjectFacts

MAX_SECTION_LINES = 40
MAX_DESCRIPTION_LINES = 5
REDACTION_MARKER = "[redacted"
UNSAFE_HTML = re.compile(r"<\s*(?:script|iframe|object|embed)\b|javascript:", re.I)
URL = re.compile(r"https?://[^\s<>()\[\]`'\"]+")
JS_TOOLS = re.compile(r"\b(?:npm|pnpm|yarn)\b")
GLOBAL_INSTALL = re.compile(r"\s(?:-g|--global)\b")
PYTHON_TOOLS = re.compile(r"(?<![\w.-])(?:pip3?|pytest|poetry|pipenv)\b")


class ReadmeError(Exception):
    """The proposal was rejected whole. The message is safe to show."""


@dataclass(frozen=True)
class Section:
    topic: str
    heading: str
    body: str


@dataclass(frozen=True)
class ReadmePlan:
    change: FileChange | None  # None: nothing to add
    creates: bool  # True: a new README (change.before is "")
    added: tuple[tuple[str, str], ...]  # (topic, heading)
    dropped: tuple[tuple[str, str], ...]  # (what, why)
    links: tuple[str, ...]  # URLs the AI wrote, for the user to check


def plan_readme(
    path: PurePosixPath,
    before: str | None,
    sections: Sequence[tuple[str, str, str]],
    description: str,
    asked: Sequence[str],
    project_name: str,
    facts: ProjectFacts,
    root: Path,
    files: tuple[PurePosixPath, ...],
) -> ReadmePlan:
    """The change that adds `sections` (topic, heading, body) to the README.

    `before` is None when there is no README yet: then a new one is planned.
    """
    level = section_level(before) if before is not None else 2
    kept: dict[str, Section] = {}
    dropped: list[tuple[str, str]] = []
    for raw_topic, raw_heading, raw_body in sections:
        topic = raw_topic.strip().lower()
        heading = clean_text(raw_heading).strip("#").strip()
        body = clean_text(raw_body)
        check_safe(f"the {topic or 'untitled'} section", f"{heading}\n{body}")
        why = section_problem(topic, heading, body, level, asked, kept, facts)
        if why:
            dropped.append((f"{topic or '?'} ({heading or 'no heading'})", why))
        else:
            kept[topic] = Section(topic, heading, body)

    ordered = [kept[topic] for topic in TOPICS if topic in kept]
    if not ordered:
        return ReadmePlan(None, before is None, (), tuple(dropped), ())
    urls = URL.findall("\n".join(section.body for section in ordered))
    links = tuple(dict.fromkeys(url.rstrip(".,;:") for url in urls))

    if before is None:
        intro = clean_text(description)
        check_safe("the description", intro)
        why = description_problem(intro)
        if why:
            dropped.append(("description", why))
            intro = ""
        after = new_readme(project_name, intro, ordered)
    else:
        after, start, block = add_sections(before, ordered, level)
        if not original_kept(before, after, start, block):
            raise ReadmeError("the README's own lines would change")

    prove_sections(path, before, after, ordered, root, files)
    original = before or ""
    change = FileChange(path, original, after, unified_diff(path, original, after))
    return ReadmePlan(
        change,
        before is None,
        tuple((s.topic, s.heading) for s in ordered),
        tuple(dropped),
        links,
    )


def check_safe(what: str, text: str) -> None:
    """Reject the whole proposal for a hidden line, a secret or code-running HTML."""
    if REDACTION_MARKER in text:
        raise ReadmeError(f"{what} includes a line hidden as a possible secret")
    if UNSAFE_HTML.search(text):
        raise ReadmeError(f"{what} includes HTML that runs code")
    for line in text.split("\n"):
        finding = match_line(line)
        if finding is not None:
            raise ReadmeError(f"{what} includes a possible secret ({finding.message})")


def section_problem(
    topic: str,
    heading: str,
    body: str,
    level: int,
    asked: Sequence[str],
    kept: dict[str, Section],
    facts: ProjectFacts,
) -> str | None:
    """Why a section can't be used, or None."""
    if topic not in asked:
        return "not one of the topics DevAI asked for"
    if topic in kept:
        return "a second section for the same topic"
    if not heading:
        return "no heading"
    if "\n" in heading:
        return "the heading has several lines"
    if not matches(WORD.findall(heading.lower()), TOPICS[topic]):
        return f"the heading doesn't name the {topic} section"
    if not body:
        return "no text"
    if body.count("\n") + 1 > MAX_SECTION_LINES:
        return f"too long (at most {MAX_SECTION_LINES} lines)"
    inner, code = split_markdown(body)
    if any(found.level <= level for found in inner):
        return "it has headings at the section's own level"
    if unclosed_fence(body):
        return "a code block isn't closed (it would swallow the rest of the README)"
    return command_problem(code, facts)


def command_problem(code: list[tuple[int, str]], facts: ProjectFacts) -> str | None:
    """Why a command in the section's code can't work in this project, or None."""
    for mention in script_mentions(code):
        if facts.scripts is None:
            return f"`{mention.command}` can't be checked: a package.json can't be read"
        if mention.script not in facts.scripts:
            return f"`{mention.command}` runs a script no package.json has"
    for _, line in code:
        tool = JS_TOOLS.search(line)
        if tool and not facts.has_package_json and not GLOBAL_INSTALL.search(line):
            return f"it uses {tool[0]}, but the project has no package.json"
        tool = PYTHON_TOOLS.search(line)
        if tool and not facts.has_python:
            return f"it uses {tool[0]}, but the project has no Python files"
    return None


def unclosed_fence(text: str) -> bool:
    fence = None
    for line in text.splitlines():
        marker = FENCE.match(line)
        if marker is None:
            continue
        if fence is None:
            fence = marker["fence"]
        elif marker["fence"].startswith(fence) and not line[marker.end() :].strip():
            fence = None
    return fence is not None


def description_problem(text: str) -> str | None:
    if not text:
        return "empty"
    if text.count("\n") + 1 > MAX_DESCRIPTION_LINES:
        return f"too long (at most {MAX_DESCRIPTION_LINES} lines)"
    if split_markdown(text)[0] or FENCE.search(text):
        return "it should be plain sentences, without headings or code blocks"
    return None


def section_level(text: str) -> int:
    """The README's most common section level below the title (## by default)."""
    levels = Counter(h.level for h in split_markdown(text)[0] if h.level >= 2)
    return min(levels, key=lambda level: (-levels[level], level)) if levels else 2


def section_lines(section: Section, level: int) -> list[str]:
    return ["#" * level + " " + section.heading, "", *section.body.split("\n"), ""]


def new_readme(name: str, description: str, sections: list[Section]) -> str:
    lines = [f"# {name}", ""]
    if description:
        lines += [description, ""]
    for section in sections:
        lines += section_lines(section, 2)
    return "\n".join(lines).rstrip("\n") + "\n"


def add_sections(
    before: str, sections: list[Section], level: int
) -> tuple[str, int, list[str]]:
    """(new text, index of the first added line, the added lines without endings)."""
    lines = before.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in before else "\n"
    block = [line for section in sections for line in section_lines(section, level)]
    license_heading = next(
        (
            heading
            for heading in split_markdown(before)[0]
            if 2 <= heading.level <= level and matches(heading.words, TOPICS["license"])
        ),
        None,
    )
    if license_heading is not None:
        start = license_heading.line - 1  # right before the license section
    else:
        start = len(lines)
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += newline
        block.pop()  # no blank line at the end of the file
    if start > 0 and lines[start - 1].strip():
        block.insert(0, "")  # a blank line before the new heading
    lines[start:start] = [line + newline for line in block]
    return "".join(lines), start, block


def original_kept(before: str, after: str, start: int, block: list[str]) -> bool:
    """True if removing the added block gives back the README, line by line."""
    lines = after.splitlines(keepends=True)
    remaining = lines[:start] + lines[start + len(block) :]
    original = before.splitlines(keepends=True)
    if original and not original[-1].endswith(("\n", "\r")):
        # Appending gave the last line an ending; its text must not change.
        return "".join(remaining).rstrip("\r\n") == before.rstrip("\r\n")
    return remaining == original


def prove_sections(
    path: PurePosixPath,
    before: str | None,
    after: str,
    sections: list[Section],
    root: Path,
    files: tuple[PurePosixPath, ...],
) -> None:
    """`devai docs` on the new text: every section found, no new failing command."""
    new = readme_map(path, after, root, files)
    missing = [s.topic for s in sections if s.topic not in new.sections]
    if missing:
        raise ReadmeError(f"devai docs wouldn't find the {', '.join(missing)} section")
    old_failing = set()
    if before is not None:
        old = readme_map(path, before, root, files)
        old_failing = {mention.command for mention in old.missing_scripts}
    new_failing = [
        mention.command
        for mention in new.missing_scripts
        if mention.command not in old_failing
    ]
    if new_failing:
        raise ReadmeError(f"the README would run {', '.join(new_failing)}, which fails")
