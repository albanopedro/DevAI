"""Data models shared across DevAI."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class FileSource(StrEnum):
    """How the project's file list was built."""

    GIT = "git"
    FILESYSTEM = "filesystem"
    FILESYSTEM_GITIGNORE = "filesystem + .gitignore"


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
    directories: tuple[DirectoryStat, ...] = ()
    root_file_count: int = 0
    warnings: tuple[str, ...] = ()
