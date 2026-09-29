"""Data models shared across DevAI."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath


class FileSource(StrEnum):
    """How the project's file list was built."""

    GIT = "git"
    FILESYSTEM = "filesystem"
    FILESYSTEM_GITIGNORE = "filesystem + .gitignore"


class Ecosystem(StrEnum):
    """Package ecosystem a dependency manifest belongs to."""

    NPM = "npm"
    PYTHON = "python"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    RUBY = "ruby"
    PHP = "php"
    DART = "dart"


@dataclass(frozen=True)
class Dependency:
    name: str  # normalized: Python names follow PEP 503 ("Foo_Bar" → "foo-bar")
    dev: bool = False


@dataclass(frozen=True)
class Manifest:
    """A dependency manifest such as package.json or pyproject.toml."""

    path: PurePosixPath  # relative to the project root
    ecosystem: Ecosystem
    dependencies: tuple[Dependency, ...] = ()
    parsed: bool = True  # False if unsupported or unreadable


@dataclass(frozen=True)
class TestSummary:
    """Test files found and test frameworks declared as dependencies."""

    __test__ = False  # tells pytest this is not a test class, despite the name

    files: int = 0
    frameworks: tuple[str, ...] = ()


@dataclass(frozen=True)
class LanguageStat:
    name: str
    files: int


@dataclass(frozen=True)
class DirectoryStat:
    """A top-level directory and how many files it contains (recursively)."""

    name: str
    files: int


@dataclass(frozen=True)
class ProjectInfo:
    """Basic facts about a scanned project."""

    name: str
    path: Path
    file_count: int
    file_source: FileSource
    has_git: bool
    has_readme: bool
    languages: tuple[LanguageStat, ...] = ()
    frameworks: tuple[str, ...] = ()
    manifests: tuple[Manifest, ...] = ()
    tests: TestSummary = TestSummary()
    config_files: tuple[PurePosixPath, ...] = ()
    directories: tuple[DirectoryStat, ...] = ()
    root_file_count: int = 0
    warnings: tuple[str, ...] = ()
