"""Minimal wrapper around the git command-line tool (see D007)."""

import os
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


def untracked_files(path: Path) -> list[str]:
    """New files git doesn't track yet and doesn't ignore, relative to `path`."""
    output = run_git(path, "ls-files", "--others", "--exclude-standard", "-z")
    return [name for name in output.split("\0") if name]


def has_commits(path: Path) -> bool:
    """False in a new repository whose first commit hasn't been made yet."""
    try:
        run_git(path, "rev-parse", "--verify", "--quiet", "HEAD")
    except GitError:
        return False
    return True


def empty_tree(path: Path) -> str:
    """The id of the empty tree: what "before" means in a repo with no commits."""
    return run_git(path, "hash-object", "-t", "tree", os.devnull).strip()


def merge_base(path: Path, ref: str) -> str:
    """The commit where HEAD's history split from `ref` (as in a pull request)."""
    return run_git(path, "merge-base", ref, "HEAD").strip()


def is_tracked(path: Path, file: str) -> bool:
    """True if git tracks `file` (relative to `path`)."""
    try:
        run_git(path, "--literal-pathspecs", "ls-files", "--error-unmatch", "--", file)
    except GitError:
        return False
    return True


def has_pending_changes(path: Path, file: str) -> bool:
    """True if `file` has staged or unstaged changes compared with HEAD."""
    output = run_git(
        path, "--literal-pathspecs", "status", "--porcelain=v1", "-z", "--", file
    )
    return bool(output.strip("\0"))


def is_ignored(path: Path, file: str) -> bool:
    """True if git would ignore `file` (it doesn't need to exist yet).

    check-ignore exits 0 (ignored), 1 (not ignored) or higher (error). An error
    raises GitError instead of being read as "not ignored": callers fail closed.
    It takes plain paths; pathspec magic like --literal-pathspecs is an error.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "check-ignore", "-q", "--", file],
            capture_output=True,
            encoding="utf-8",
            errors="surrogateescape",
        )
    except FileNotFoundError as error:
        raise GitError("git is not installed") from error
    if result.returncode in (0, 1):
        return result.returncode == 0
    raise GitError(result.stderr.strip() or "git check-ignore failed")
