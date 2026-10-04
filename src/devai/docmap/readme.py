"""Check the README: which sections it has, and the npm scripts it names (D048).

Sections are found by heading words, in English or Portuguese ("Installation",
"Getting started", "Instalação", "Como usar"...): an estimate. Headings inside
code blocks don't count, so a shell comment isn't mistaken for one.

Scripts are a fact, not an estimate: `npm run deploy` or `pnpm run deploy`,
written in a code block or inline code, fails without a "deploy" script.
Every package.json in the project is read, because a README often says
`cd web && npm run dev`. Prose is not read: "use npm to run tests" isn't a
command. Yarn and Bun are left out: `yarn run x` and `bun run x` also run
binaries and files, so a missing script there isn't necessarily an error.
"""

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from devai.checks.secrets import read_scannable_text

MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
LICENSE_FILE_NAMES = ("license", "licence", "copying")

# Section → heading word sequences. A heading word matches a keyword word if
# it starts with it: "install" matches "installation", "instala" "instalação".
TOPICS: dict[str, tuple[tuple[str, ...], ...]] = {
    "installation": (
        ("install",),
        ("instala",),
        ("setup",),
        ("set", "up"),
        ("getting", "started"),
        ("quick", "start"),
        ("quickstart",),
        ("requirements",),
        ("prerequisites",),
        ("requisitos",),
        ("primeiros", "passos"),
    ),
    "usage": (
        ("usage",),
        ("uso",),
        ("how", "to", "use"),
        ("como", "usar"),
        ("example",),
        ("exemplo",),
        ("running",),
        ("como", "rodar"),
        ("como", "executar"),
        ("como", "ligar"),
        ("como", "iniciar"),
        ("commands",),
        ("comandos",),
    ),
    "tests": (("test",),),
    "license": (("licen",),),
}

ATX_HEADING = re.compile(r" {0,3}(?P<hashes>#{1,6})(?:\s+(?P<text>.*?))?\s*#*\s*")
SETEXT_UNDERLINE = re.compile(r" {0,3}(?:=+|-{2,})\s*")
FENCE = re.compile(r" {0,3}(?P<fence>`{3,}|~{3,})")
INLINE_CODE = re.compile(r"(?P<ticks>`+)(?P<code>.+?)(?P=ticks)")
WORD = re.compile(r"\w+")

# `npm run x`, `npm run-script x`, `pnpm --filter web run x`. The gap between
# the tool and "run" can't cross `&&`, `;` or `|`: that's another command.
RUN_SCRIPT = re.compile(
    r"\b(?P<tool>npm|pnpm)\b[^\n`;&|]*?\s(?:run|run-script)\s+"
    r"(?P<script>[\w@][\w:.@/+-]*)"
)
# Shortcuts that run a script by its name.
SHORTCUT = re.compile(r"\b(?P<tool>npm|pnpm)\s+(?P<script>test|t|start)\b")


@dataclass(frozen=True)
class Heading:
    line: int  # 1-based; for an underlined (setext) heading, the text's line
    level: int
    words: tuple[str, ...]  # lowercase


@dataclass(frozen=True)
class ScriptMention:
    command: str  # as DevAI writes it: "npm run deploy"
    script: str
    line: int


@dataclass(frozen=True)
class ReadmeMap:
    path: PurePosixPath
    checked: bool  # False if not Markdown or not readable: nothing below is known
    sections: tuple[str, ...] = ()  # found, in TOPICS order
    missing_sections: tuple[str, ...] = ()
    license_file: PurePosixPath | None = None  # covers "license" without a heading
    scripts_mentioned: int = 0
    missing_scripts: tuple[ScriptMention, ...] = ()
    scripts_checked: bool = True  # False if a package.json couldn't be read


def find_readme(files: Iterable[PurePosixPath]) -> PurePosixPath | None:
    """The root README, preferring Markdown, then the shortest name (README.md)."""
    candidates = [
        path
        for path in files
        if len(path.parts) == 1 and path.name.lower().startswith("readme")
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda path: (
            path.suffix.lower() not in MARKDOWN_SUFFIXES,
            len(path.name),
            path.name,
        ),
    )


def check_readme(root: Path, files: tuple[PurePosixPath, ...]) -> ReadmeMap | None:
    """None if the project has no README at its root."""
    path = find_readme(files)
    if path is None:
        return None
    text = read_scannable_text(root / path, path)
    if path.suffix.lower() not in MARKDOWN_SUFFIXES or text is None:
        return ReadmeMap(path, checked=False)
    return readme_map(path, text, root, files)


def readme_map(
    path: PurePosixPath, text: str, root: Path, files: tuple[PurePosixPath, ...]
) -> ReadmeMap:
    """The checks above on Markdown `text` (also used on a README not yet written)."""
    headings, code = split_markdown(text)
    license_file = find_license_file(files)
    found = [
        topic
        for topic, keywords in TOPICS.items()
        if any(matches(heading.words, keywords) for heading in headings)
        or (topic == "license" and license_file is not None)
    ]
    mentions = script_mentions(code)
    scripts = package_scripts(root, files) if mentions else frozenset()
    return ReadmeMap(
        path,
        checked=True,
        sections=tuple(found),
        missing_sections=tuple(topic for topic in TOPICS if topic not in found),
        license_file=license_file,
        scripts_mentioned=len(mentions),
        missing_scripts=tuple(
            mention
            for mention in mentions
            if scripts is not None and mention.script not in scripts
        ),
        scripts_checked=scripts is not None,
    )


def split_markdown(text: str) -> tuple[list[Heading], list[tuple[int, str]]]:
    """The headings and the code (line number, code text), outside and inside code."""
    headings: list[Heading] = []
    code: list[tuple[int, str]] = []
    fence = None  # the opening fence, while inside a code block
    previous = ""
    for number, line in enumerate(text.splitlines(), start=1):
        marker = FENCE.match(line)
        if fence is not None:
            closing = (
                marker is not None
                and marker["fence"].startswith(fence)  # same character, as long
                and not line[marker.end() :].strip()
            )
            if closing:
                fence = None
            else:
                code.append((number, line))
            previous = ""
        elif marker is not None:
            fence = marker["fence"]
            previous = ""
        else:
            heading = ATX_HEADING.fullmatch(line)
            if heading is not None:
                words = WORD.findall((heading["text"] or "").lower())
                headings.append(Heading(number, len(heading["hashes"]), tuple(words)))
            elif previous.strip() and SETEXT_UNDERLINE.fullmatch(line):
                level = 1 if line.strip().startswith("=") else 2
                words = WORD.findall(previous.lower())
                headings.append(Heading(number - 1, level, tuple(words)))
            code += [(number, span["code"]) for span in INLINE_CODE.finditer(line)]
            previous = line
    return headings, code


def matches(heading: Sequence[str], keywords: tuple[tuple[str, ...], ...]) -> bool:
    """True if a keyword's words start consecutive words of the heading."""
    for keyword in keywords:
        for start in range(len(heading) - len(keyword) + 1):
            pairs = zip(heading[start : start + len(keyword)], keyword, strict=True)
            if all(word.startswith(part) for word, part in pairs):
                return True
    return False


def find_license_file(files: Iterable[PurePosixPath]) -> PurePosixPath | None:
    return next(
        (
            path
            for path in sorted(files)
            if len(path.parts) == 1 and path.name.lower().startswith(LICENSE_FILE_NAMES)
        ),
        None,
    )


def script_mentions(code: list[tuple[int, str]]) -> list[ScriptMention]:
    """Each npm script the code runs, once, at its first line."""
    mentions: dict[tuple[str, str], ScriptMention] = {}

    def add(tool: str, words: str, script: str, line: int) -> None:
        mention = ScriptMention(f"{tool} {words}", script, line)
        mentions.setdefault((tool, script), mention)

    for number, text in code:
        for match in RUN_SCRIPT.finditer(text):
            script = match["script"].rstrip(".,:")
            add(match["tool"], f"run {script}", script, number)
        for match in SHORTCUT.finditer(text):
            if match["script"] == "t" and match["tool"] != "npm":
                continue  # `t` is an npm alias only
            script = "test" if match["script"] == "t" else match["script"]
            add(match["tool"], match["script"], script, number)
    return list(mentions.values())


def package_scripts(
    root: Path, files: tuple[PurePosixPath, ...]
) -> frozenset[str] | None:
    """Every script name in the project's package.json files.

    None if one of them can't be read: a missing script couldn't be told
    apart from one in the unreadable file. With no "start" script, `npm
    start` runs `node server.js`, so a server.js next to a package.json
    counts as "start".
    """
    names: set[str] = set()
    for path in files:
        if path.name != "package.json":
            continue
        text = read_scannable_text(root / path, path)
        try:
            data = json.loads(text) if text is not None else None
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            return None
        scripts = data.get("scripts", {})
        if isinstance(scripts, dict):
            names.update(scripts)
        if path.parent / "server.js" in files:
            names.add("start")
    return frozenset(names)
