"""List the files that belong to a project, honoring ignore rules.

Two strategies:
- git: when the project is inside a git work tree, git lists the files and
  applies every ignore rule itself (see D015).
- filesystem: otherwise, walk the directory, skip DEFAULT_IGNORED_DIRS and
  apply the root .gitignore with pathspec. Nested .gitignore files are not
  read in this mode.

Only file *names* are read here, never file contents (except .gitignore).
"""

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pathspec

from devai import git
from devai.models import FileSource

# Directories that are never part of the project's own source.
DEFAULT_IGNORED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "dist",
        "build",
    }
)


@dataclass(frozen=True)
class FileListing:
    files: list[PurePosixPath]  # relative to the project root, sorted
    source: FileSource


def list_project_files(root: Path) -> FileListing:
    """List project files under `root`, preferring git when available."""
    if git.is_inside_work_tree(root):
        try:
            return FileListing(list_with_git(root), FileSource.GIT)
        except git.GitError:
            pass  # fall back to the filesystem walk below

    spec = load_gitignore(root)
    source = FileSource.FILESYSTEM_GITIGNORE if spec else FileSource.FILESYSTEM
    return FileListing(list_with_filesystem(root, spec), source)


def list_with_git(root: Path) -> list[PurePosixPath]:
    # --cached also lists tracked files deleted from disk; keep only real files.
    return sorted(
        PurePosixPath(name) for name in git.list_files(root) if (root / name).is_file()
    )


def list_with_filesystem(
    root: Path, spec: pathspec.GitIgnoreSpec | None = None
) -> list[PurePosixPath]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        relative_dir = PurePosixPath(Path(dirpath).relative_to(root).as_posix())

        # Editing dirnames in place tells os.walk not to descend into them.
        dirnames[:] = [
            name
            for name in dirnames
            if name not in DEFAULT_IGNORED_DIRS
            and not is_ignored(spec, relative_dir / name, is_dir=True)
        ]
        files.extend(
            relative_dir / name
            for name in filenames
            if not is_ignored(spec, relative_dir / name)
        )
    return sorted(files)


def load_gitignore(root: Path) -> pathspec.GitIgnoreSpec | None:
    """Parse `root/.gitignore`, or return None if there isn't one."""
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return None
    lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    return pathspec.GitIgnoreSpec.from_lines(lines)


def is_ignored(
    spec: pathspec.GitIgnoreSpec | None, path: PurePosixPath, is_dir: bool = False
) -> bool:
    if spec is None:
        return False
    # A trailing slash lets directory-only patterns like "logs/" match.
    return spec.match_file(f"{path}/" if is_dir else str(path))
