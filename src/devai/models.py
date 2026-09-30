"""Data models shared across DevAI."""

from dataclasses import dataclass, field
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


class Severity(StrEnum):
    """How serious a finding is, declared from least to most severe.

    Compare severities with `rank`, never with `<`: StrEnum members compare
    as plain strings, and "high" < "low" alphabetically.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return list(Severity).index(self)


@dataclass(frozen=True)
class Finding:
    """A problem detected in the project (D009)."""

    rule_id: str
    severity: Severity
    message: str
    file: PurePosixPath | None = None
    line: int | None = None
    evidence: str | None = None  # masked: never a full secret (D010, D021)


@dataclass(frozen=True)
class SecretScanStats:
    scanned: int = 0
    skipped: int = 0  # never opened or not scannable (env, lock, binary...)


@dataclass(frozen=True)
class CheckReport:
    """Results of all checks: problems found and checks that passed."""

    findings: tuple[Finding, ...] = ()
    passed: tuple[str, ...] = ()
    secret_scan: SecretScanStats = SecretScanStats()


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
    # Every project file, relative to `path`. Used by checks; hidden from repr.
    files: tuple[PurePosixPath, ...] = field(default=(), repr=False)


@dataclass(frozen=True)
class ChangedFile:
    """A file in the changes `devai review` looks at."""

    path: PurePosixPath  # relative to the reviewed directory
    status: str  # git's letter: A(dded), M(odified), D(eleted), R(enamed), T(ype)
    additions: int | None = None  # None: not counted (binary, or not read)
    deletions: int | None = None
    old_path: PurePosixPath | None = None  # renames only
    untracked: bool = False


@dataclass(frozen=True)
class ReviewReport:
    """The result of `devai review`. It never contains the changed code itself."""

    name: str
    path: Path
    description: str  # which changes: working tree, staged, or since a base
    files: tuple[ChangedFile, ...]
    checks: CheckReport
