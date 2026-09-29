"""Data models shared across DevAI."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectInfo:
    """Basic facts about a scanned project."""

    name: str
    path: Path
    file_count: int
    has_git: bool
    has_readme: bool
