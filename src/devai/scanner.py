"""Walk a project directory and collect basic information."""

import os
from pathlib import Path

from devai.models import ProjectInfo

# Directories that are never part of the project's own source.
# Replaced by real .gitignore support in Phase 2a.
IGNORED_DIRS = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
)


def scan_project(root: Path) -> ProjectInfo:
    """Scan `root` and return basic project information.

    Raises NotADirectoryError if `root` is not an existing directory.
    """
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    return ProjectInfo(
        name=root.name,
        path=root,
        file_count=count_files(root),
        has_git=(root / ".git").exists(),
        has_readme=has_readme(root),
    )


def count_files(root: Path) -> int:
    """Count files under `root`, skipping ignored directories and symlinked dirs."""
    total = 0
    for _dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Editing dirnames in place tells os.walk not to descend into them.
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        total += len(filenames)
    return total


def has_readme(root: Path) -> bool:
    """Return True if `root` contains a README file (any extension or case)."""
    return any(
        entry.is_file() and entry.name.lower().startswith("readme")
        for entry in root.iterdir()
    )
