"""Minimal wrapper around the git command-line tool (see D007)."""

import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when git is missing or a git command fails."""


def run_git(repo: Path, *args: str) -> str:
    """Run `git -C repo <args>` and return its stdout."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            encoding="utf-8",
            # Keep undecodable bytes in file names instead of crashing.
            errors="surrogateescape",
        )
    except FileNotFoundError as error:
        raise GitError("git is not installed") from error

    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout


def is_inside_work_tree(path: Path) -> bool:
    """Return True if `path` is inside a git working tree."""
    try:
        return run_git(path, "rev-parse", "--is-inside-work-tree").strip() == "true"
    except GitError:
        return False


def list_files(path: Path) -> list[str]:
    """List tracked and untracked, non-ignored files under `path`.

    Paths are relative to `path`. Git applies every ignore rule itself:
    nested .gitignore files, .git/info/exclude and the global excludes file.
    """
    output = run_git(
        path, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
    )
    return [name for name in output.split("\0") if name]
