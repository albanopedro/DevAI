"""Find dependency manifests and read the dependencies they declare.

Manifests are the only files opened in this module. Parsed formats:
package.json (npm), pyproject.toml and requirements*.txt (Python).
Other manifests (go.mod, Cargo.toml...) are detected but not parsed.
"""

import json
import re
import tomllib
from collections.abc import Callable, Iterable
from functools import partial
from pathlib import Path, PurePosixPath

from devai.models import Dependency, Ecosystem, Manifest

Parser = Callable[[str], list[Dependency]]

UNPARSED_MANIFESTS = {
    "go.mod": Ecosystem.GO,
    "Cargo.toml": Ecosystem.RUST,
    "pom.xml": Ecosystem.JAVA,
    "build.gradle": Ecosystem.JAVA,
    "build.gradle.kts": Ecosystem.JAVA,
    "Gemfile": Ecosystem.RUBY,
    "composer.json": Ecosystem.PHP,
    "pubspec.yaml": Ecosystem.DART,
}

# pyproject optional-dependencies groups treated as development-only.
DEV_GROUPS = frozenset({"dev", "test", "tests", "testing", "lint", "docs", "typing"})

REQUIREMENTS_FILE = re.compile(r".*requirements.*\.txt", re.IGNORECASE)
DEV_REQUIREMENTS_HINT = re.compile(r"dev|test|lint|doc", re.IGNORECASE)

# Name at the start of a PEP 508 requirement, e.g. "fastapi" in
# "fastapi[standard]>=0.100; python_version>='3.11'". Deliberately simple.
PEP508_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")


def detect_manifests(
    root: Path, files: Iterable[PurePosixPath]
) -> tuple[tuple[Manifest, ...], tuple[str, ...]]:
    """Return (manifests found in `files`, warnings for unreadable ones)."""
    manifests = []
    warnings = []
    for path in files:
        identified = identify_manifest(path)
        if identified is None:
            continue

        ecosystem, parser = identified
        if parser is None:
            manifests.append(Manifest(path, ecosystem, parsed=False))
            continue

        try:
            dependencies = parser((root / path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            # JSON/TOML decode errors and UnicodeDecodeError are ValueErrors.
            warnings.append(f"Could not parse {path}: {error}")
            manifests.append(Manifest(path, ecosystem, parsed=False))
            continue

        manifests.append(Manifest(path, ecosystem, unique(dependencies)))
    return tuple(manifests), tuple(warnings)


def identify_manifest(path: PurePosixPath) -> tuple[Ecosystem, Parser | None] | None:
    """Return (ecosystem, parser or None) if `path` is a known manifest."""
    name = path.name
    if name == "package.json":
        return Ecosystem.NPM, parse_package_json
    if name == "pyproject.toml":
        return Ecosystem.PYTHON, parse_pyproject
    if REQUIREMENTS_FILE.fullmatch(name):
        is_dev = DEV_REQUIREMENTS_HINT.search(name) is not None
        return Ecosystem.PYTHON, partial(parse_requirements, dev=is_dev)
    if name in UNPARSED_MANIFESTS:
        return UNPARSED_MANIFESTS[name], None
    return None


# --- npm -------------------------------------------------------------------


def parse_package_json(text: str) -> list[Dependency]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return [
        *npm_section(data, "dependencies", dev=False),
        *npm_section(data, "devDependencies", dev=True),
    ]


def npm_section(data: dict, key: str, dev: bool) -> list[Dependency]:
    section = data.get(key, {})
    if not isinstance(section, dict):
        raise ValueError(f'"{key}" must be an object')
    return [Dependency(name, dev) for name in section]


# --- Python ----------------------------------------------------------------


def parse_pyproject(text: str) -> list[Dependency]:
    data = tomllib.loads(text)
    project = table(data, "project")

    dependencies = from_requirements(project.get("dependencies", []), dev=False)
    for group, requirements in table(project, "optional-dependencies").items():
        is_dev = group.lower() in DEV_GROUPS
        dependencies += from_requirements(requirements, dev=is_dev)
    # PEP 735 dependency groups are development-only by design.
    for requirements in table(data, "dependency-groups").values():
        dependencies += from_requirements(requirements, dev=True)
    return dependencies


def parse_requirements(text: str, dev: bool = False) -> list[Dependency]:
    requirements = []
    for line in text.splitlines():
        line = line.split(" #", 1)[0].strip()
        # Skip blanks, comments and pip options such as -r, -e, --index-url.
        if line and not line.startswith(("#", "-")):
            requirements.append(line)
    return from_requirements(requirements, dev)


def from_requirements(requirements: object, dev: bool) -> list[Dependency]:
    """Turn a list of PEP 508 strings into dependencies, skipping bad entries."""
    if not isinstance(requirements, list):
        return []
    names = (python_name(item) for item in requirements if isinstance(item, str))
    return [Dependency(name, dev) for name in names if name is not None]


def python_name(requirement: str) -> str | None:
    """Extract and normalize the package name, or None (URLs, local paths)."""
    requirement = requirement.strip()
    if URL.match(requirement):
        return None
    match = PEP508_NAME.match(requirement)
    return normalize_python_name(match.group()) if match else None


def normalize_python_name(name: str) -> str:
    """PEP 503 normalization: "Django" == "django", "typing_extensions" == ..."""
    return re.sub(r"[-_.]+", "-", name).lower()


# --- helpers ---------------------------------------------------------------


def table(data: dict, key: str) -> dict:
    """Return data[key] if it is a table (dict), else an empty dict."""
    value = data.get(key, {})
    return value if isinstance(value, dict) else {}


def unique(dependencies: Iterable[Dependency]) -> tuple[Dependency, ...]:
    """Drop duplicate names, keeping first-seen order; runtime beats dev."""
    by_name: dict[str, Dependency] = {}
    for dependency in dependencies:
        current = by_name.get(dependency.name)
        if current is None or (current.dev and not dependency.dev):
            by_name[dependency.name] = dependency
    return tuple(by_name.values())
