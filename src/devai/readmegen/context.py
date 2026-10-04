"""What a README proposal may receive, and which sections to ask for (D050).

Allow-listed: the project summary of D025, the README itself (lines that may
hold a secret replaced, at most MAX_README_LINES), the topics to write, and
the scripts the project defines (package.json scripts, pyproject.toml
[project.scripts]), so commands can be written from facts. No source code.

Topics are asked only when the project backs them: "tests" only if there are
test files, and "license" never, because choosing a license is the owner's
decision, not the AI's.
"""

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from devai.ai.context import build_context
from devai.analyzer.languages import language_for
from devai.checks.secrets import read_scannable_text, redact_line
from devai.docmap.readme import TOPICS, ReadmeMap, package_scripts
from devai.models import CheckReport, ProjectInfo

# Bump when the structure of the context changes.
README_CONTEXT_VERSION = 1

MAX_README_LINES = 400
MAX_SCRIPT_FILES = 5
MAX_SCRIPTS_PER_FILE = 30
PYTHON_MANIFESTS = frozenset({"pyproject.toml", "requirements.txt", "Pipfile"})


@dataclass(frozen=True)
class ProjectFacts:
    """What README commands are checked against."""

    scripts: frozenset[str] | None  # npm script names; None if one can't be read
    has_package_json: bool
    has_python: bool


def project_facts(info: ProjectInfo) -> ProjectFacts:
    return ProjectFacts(
        scripts=package_scripts(info.path, info.files),
        has_package_json=any(path.name == "package.json" for path in info.files),
        has_python=any(
            language_for(path) == "Python" or path.name in PYTHON_MANIFESTS
            for path in info.files
        ),
    )


def readme_topics(
    info: ProjectInfo, readme: ReadmeMap | None
) -> tuple[list[str], list[tuple[str, str]]]:
    """(topics to ask for, topics left out with the reason), in TOPICS order."""
    missing = list(TOPICS) if readme is None else list(readme.missing_sections)
    asked = []
    left_out = []
    for topic in missing:
        if topic == "license":
            left_out.append(
                (topic, "choosing a license is your decision: add a LICENSE file")
            )
        elif topic == "tests" and not info.tests.files:
            left_out.append((topic, "the project has no tests to describe"))
        else:
            asked.append(topic)
    return asked, left_out


def build_readme_context(
    info: ProjectInfo,
    checks: CheckReport,
    readme_path: PurePosixPath | None,
    readme_text: str | None,
    topics: list[str],
) -> dict[str, Any]:
    """Return the JSON-serializable context a README proposal may receive."""
    truncated: dict[str, dict[str, int]] = {}
    redacted = 0

    lines = [] if readme_text is None else readme_text.split("\n")
    if len(lines) > MAX_README_LINES:
        truncated["readme"] = {"shown": MAX_README_LINES, "total": len(lines)}
        lines = lines[:MAX_README_LINES]
    safe_lines = []
    for line in lines:
        safe, was_redacted = redact_line(line.removesuffix("\r"))
        safe_lines.append(safe)
        redacted += was_redacted

    scripts, scripts_redacted = defined_scripts(info.path, info.files, truncated)
    return {
        "readme_context_version": README_CONTEXT_VERSION,
        "project": build_context(info, checks),  # the allow-listed summary (D025)
        "readme": {
            "path": str(readme_path) if readme_path else None,
            "exists": readme_text is not None,
            "content": "\n".join(safe_lines),
        },
        "topics": topics,
        "scripts": scripts,
        "redacted_lines": redacted + scripts_redacted,
        "truncated": truncated,
    }


def defined_scripts(
    root: Path, files: tuple[PurePosixPath, ...], truncated: dict[str, dict[str, int]]
) -> tuple[dict[str, dict[str, Any]], int]:
    """manifest path → how its scripts run, and {name: command}, redacted.

    "run_with" is spelled out because a real model, given only
    {"notes": "notes.cli:main"}, didn't see that `notes` is the command.
    """
    found: dict[str, dict[str, str]] = {}
    for path in files:
        if path.name == "package.json":
            data = read_json(root, path)
            scripts = data.get("scripts") if isinstance(data, dict) else None
        elif path == PurePosixPath("pyproject.toml"):
            data = read_toml(root, path)
            project = data.get("project", {}) if isinstance(data, dict) else {}
            scripts = project.get("scripts") if isinstance(project, dict) else None
        else:
            continue
        if isinstance(scripts, dict) and scripts:
            found[str(path)] = {
                str(name): str(command) for name, command in scripts.items()
            }

    kept: dict[str, dict[str, Any]] = {}
    redacted = 0
    for path, scripts in list(found.items())[:MAX_SCRIPT_FILES]:
        names = list(scripts)[:MAX_SCRIPTS_PER_FILE]
        if len(names) < len(scripts):
            truncated[f"scripts:{path}"] = {"shown": len(names), "total": len(scripts)}
        safe_scripts = {}
        for name in names:
            safe, was_redacted = redact_line(scripts[name])
            safe_scripts[name] = safe
            redacted += was_redacted
        how = run_with(PurePosixPath(path))
        kept[path] = {"run_with": how, "scripts": safe_scripts}
    if len(found) > MAX_SCRIPT_FILES:
        truncated["scripts"] = {"shown": MAX_SCRIPT_FILES, "total": len(found)}
    return kept, redacted


def run_with(path: PurePosixPath) -> str:
    if path.name == "pyproject.toml":
        return "<name>: a command, available after installing the package"
    where = "" if path.parent == PurePosixPath(".") else f", from {path.parent}/"
    return f"npm run <name> (npm test and npm start for those two){where}"


def read_json(root: Path, path: PurePosixPath) -> object:
    text = read_scannable_text(root / path, path)
    try:
        return json.loads(text) if text is not None else None
    except json.JSONDecodeError:
        return None


def read_toml(root: Path, path: PurePosixPath) -> object:
    text = read_scannable_text(root / path, path)
    try:
        return tomllib.loads(text) if text is not None else None
    except tomllib.TOMLDecodeError:
        return None
