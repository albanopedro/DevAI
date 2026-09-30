"""Collect the changes `devai review` looks at, from git.

Two steps, so a file's content is read only when the rules allow it:
1. the list of changed files: names, statuses and line counts only;
2. the added lines, only for files that aren't skipped. A real .env file is
   never read, not even through its diff (the diff would contain its values).
   Lock, minified, binary, symlinked and large files follow the secret
   scanning rules (D021).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from devai import git
from devai.checks.secrets import MAX_FILE_SIZE, is_skipped_by_name, read_scannable_text
from devai.models import ChangedFile

HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class ReviewError(Exception):
    """The changes can't be collected; the message is safe to show."""


@dataclass(frozen=True)
class AddedLine:
    number: int  # line number in the new version of the file
    text: str


@dataclass(frozen=True)
class Changes:
    root: Path
    description: str
    files: tuple[ChangedFile, ...]
    # Added lines per file, kept in memory for the checks and never reported.
    added_lines: dict[PurePosixPath, tuple[AddedLine, ...]] = field(
        default_factory=dict
    )
    skipped: tuple[PurePosixPath, ...] = ()  # changed files whose content wasn't read


def collect_changes(
    path: Path, staged: bool = False, base: str | None = None
) -> Changes:
    """Collect the changes under `path`.

    Default: the working tree against HEAD (staged, unstaged and untracked).
    `staged`: only what the next commit would contain.
    `base`: committed changes since the branch left `base` (like a pull request).
    Raises NotADirectoryError or ReviewError.
    """
    root = path.resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    if not git.is_inside_work_tree(root):
        raise ReviewError(
            f"devai review needs a git repository, and {root} isn't in one."
        )

    range_args, description = diff_range(root, staged, base)
    tracked = tracked_changes(root, range_args)

    added_lines: dict[PurePosixPath, tuple[AddedLine, ...]] = {}
    skipped: list[PurePosixPath] = []
    files: list[ChangedFile] = []
    for file in tracked:
        files.append(file)
        if file.status == "D" or file.additions == 0:
            continue  # nothing added: nothing to read
        if file.additions is None or not may_read(root, file.path):
            skipped.append(file.path)
            continue
        added_lines[file.path] = added_lines_from_git(root, range_args, file)

    if not staged and base is None:
        for name in git.untracked_files(root):
            file, lines = untracked_file(root, PurePosixPath(name))
            files.append(file)
            if lines is None:
                skipped.append(file.path)
            else:
                added_lines[file.path] = lines

    return Changes(
        root=root,
        description=description,
        files=tuple(sorted(files, key=lambda file: str(file.path))),
        added_lines=added_lines,
        skipped=tuple(sorted(skipped, key=str)),
    )


def diff_range(root: Path, staged: bool, base: str | None) -> tuple[list[str], str]:
    """The `git diff` arguments that select the changes, and a description."""
    if base is not None:
        try:
            start = git.merge_base(root, base)
        except git.GitError as error:
            raise ReviewError(f"Can't compare with {base!r}: {error}") from error
        return [start, "HEAD"], f"committed changes since {base} ({start[:7]})"

    # In a repository without commits, "before" is the empty tree.
    head = "HEAD" if git.has_commits(root) else git.empty_tree(root)
    if staged:
        return ["--cached", head], "staged changes (what the next commit would contain)"
    return [head], "working tree vs HEAD (staged, unstaged and untracked)"


def tracked_changes(root: Path, range_args: list[str]) -> list[ChangedFile]:
    """Changed tracked files with statuses and line counts (no content)."""

    def diff(output_option: str) -> str:
        return git.run_git(
            root, "diff", output_option, "--relative", "-z", "-M", *range_args
        )

    statuses = parse_name_status(diff("--name-status"))
    counts = parse_numstat(diff("--numstat"))
    return [
        ChangedFile(path, status, *counts.get(path, (None, None)), old_path=old_path)
        for status, old_path, path in statuses
    ]


def parse_name_status(
    output: str,
) -> list[tuple[str, PurePosixPath | None, PurePosixPath]]:
    """Parse `git diff --name-status -z`: "M\\0path\\0" or "R100\\0old\\0new\\0"."""
    tokens = output.split("\0")
    entries = []
    index = 0
    while index < len(tokens) and tokens[index]:
        status = tokens[index][0]
        if status in "RC":
            old, new = tokens[index + 1], tokens[index + 2]
            entries.append((status, PurePosixPath(old), PurePosixPath(new)))
            index += 3
        else:
            entries.append((status, None, PurePosixPath(tokens[index + 1])))
            index += 2
    return entries


def parse_numstat(output: str) -> dict[PurePosixPath, tuple[int | None, int | None]]:
    """Parse `git diff --numstat -z`.

    Entries are "added\\tdeleted\\tpath\\0"; a rename leaves the path empty and
    adds "old\\0new\\0". Binary files show "-" for counts: they become None.
    """
    tokens = output.split("\0")
    counts = {}
    index = 0
    while index < len(tokens) and tokens[index]:
        added, deleted, path = tokens[index].split("\t", 2)
        if path:
            index += 1
        else:  # rename: the old and new paths follow
            path = tokens[index + 2]
            index += 3
        counts[PurePosixPath(path)] = (
            None if added == "-" else int(added),
            None if deleted == "-" else int(deleted),
        )
    return counts


def may_read(root: Path, path: PurePosixPath) -> bool:
    """Apply the privacy and size rules before reading a changed file's diff."""
    if is_skipped_by_name(path):
        return False
    try:
        file = root / path
        return not file.is_symlink() and file.stat().st_size <= MAX_FILE_SIZE
    except OSError:
        return True  # not on disk (e.g. only in the index): git has the content


def added_lines_from_git(
    root: Path, range_args: list[str], file: ChangedFile
) -> tuple[AddedLine, ...]:
    """The lines `file` adds, read from a diff limited to that file."""
    paths = [str(file.path)] + ([str(file.old_path)] if file.old_path else [])
    patch = git.run_git(
        root,
        "--literal-pathspecs",  # a name like "*.py" is a file, not a pattern
        "diff",
        "--relative",
        "-U0",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "-M",
        *range_args,
        "--",
        *paths,
    )
    return parse_added_lines(patch)


def parse_added_lines(patch: str) -> tuple[AddedLine, ...]:
    """Added lines of a one-file unified diff, numbered as in the new file."""
    added = []
    number = None  # None until the first hunk: skips "diff", "---", "+++" headers
    # split("\n"), not splitlines(): a form feed inside a line isn't a new line.
    for line in patch.split("\n"):
        header = HUNK_HEADER.match(line)
        if header:
            number = int(header.group(1))
        elif number is None:
            continue
        elif line.startswith("+"):
            added.append(AddedLine(number, line[1:]))
            number += 1
        elif line.startswith(" "):
            number += 1  # context line (none with -U0, kept for safety)
        # "-" (removed) and "\ No newline at end of file" don't move the counter
    return tuple(added)


def untracked_file(
    root: Path, path: PurePosixPath
) -> tuple[ChangedFile, tuple[AddedLine, ...] | None]:
    """A new file git doesn't track yet: every line is an added line."""
    text = None if is_skipped_by_name(path) else read_scannable_text(root / path, path)
    if text is None:
        return ChangedFile(path, "A", untracked=True), None

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # a final newline doesn't start another line
    added = tuple(
        AddedLine(number, line.removesuffix("\r"))
        for number, line in enumerate(lines, start=1)
    )
    return ChangedFile(path, "A", len(added), 0, untracked=True), added
