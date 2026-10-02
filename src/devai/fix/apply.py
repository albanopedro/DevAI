"""Write a validated fix to disk, only when every safety check passes (D044).

Before the AI is asked (check_can_apply):
- the project is in a git repository, and each named file is tracked and has
  no pending changes, so `git restore <file>` undoes the fix;
- each file is valid UTF-8, so rewriting it can't corrupt bytes.

When writing (apply_changes):
- each file must still hold exactly the content the fix was proposed for,
  and git must still see it unchanged;
- each new version is written to a temporary file in the same directory,
  with the original's permissions, then swapped in with os.replace;
- with several files, a failed swap restores the files already written.

DevAI only reads git here. It never stages, commits or runs anything else.
"""

import os
import shutil
import tempfile
from pathlib import Path

from devai import git
from devai.chat.retrieval import SelectedFile
from devai.fix.edits import FileChange


class ApplyError(Exception):
    """A safety check failed. Nothing was written; the message is safe to show."""


class WriteError(Exception):
    """Writing failed midway; files already written were restored."""


def check_can_apply(root: Path, files: list[SelectedFile]) -> None:
    """Refuse early, before any AI call, when a fix couldn't be undone safely."""
    if not git.is_inside_work_tree(root):
        raise ApplyError(
            "--apply needs a git repository, so the fix can be undone with git restore"
        )
    for selected in files:
        name = str(selected.path)
        if not git.is_tracked(root, name):
            raise ApplyError(
                f"{name} isn't tracked by git: commit it first, so the fix can be "
                "undone"
            )
        if git.has_pending_changes(root, name):
            raise ApplyError(
                f"{name} has uncommitted changes: commit or stash them first, so the "
                "fix can be undone with git restore"
            )
        try:
            text = (root / selected.path).read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise ApplyError(
                f"{name} isn't valid UTF-8; DevAI won't rewrite it"
            ) from None
        if text != selected.text:
            raise ApplyError(f"{name} changed while it was being read")


def apply_changes(root: Path, changes: list[FileChange]) -> None:
    """Write every change, or none of them."""
    for change in changes:
        target = root / change.path
        if target.read_bytes() != change.before.encode("utf-8"):
            raise ApplyError(
                f"{change.path} changed after the fix was proposed; nothing was written"
            )
        if git.has_pending_changes(root, str(change.path)):
            raise ApplyError(
                f"{change.path} has uncommitted changes now; nothing was written"
            )

    prepared: list[tuple[Path, Path, FileChange]] = []
    try:
        for change in changes:
            target = root / change.path
            prepared.append((write_temporary(target, change.after), target, change))
    except OSError as error:
        remove_temporaries(prepared)
        raise WriteError(
            f"couldn't prepare the new files ({error}); nothing was written"
        ) from error

    written: list[tuple[Path, FileChange]] = []
    for index, (temporary, target, change) in enumerate(prepared):
        try:
            os.replace(temporary, target)
        except OSError as error:
            remove_temporaries(prepared[index:])
            for done_target, done_change in written:
                done_target.write_bytes(done_change.before.encode("utf-8"))
            raise WriteError(
                f"writing {change.path} failed ({error}); the files already written "
                "were restored"
            ) from error
        written.append((target, change))


def write_temporary(target: Path, text: str) -> Path:
    """The new content in a temporary file next to `target`, same permissions."""
    descriptor, name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".devai-tmp"
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(text.encode("utf-8"))  # exact bytes: line endings kept
            handle.flush()
            os.fsync(handle.fileno())
        shutil.copymode(target, temporary)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def remove_temporaries(prepared: list[tuple[Path, Path, FileChange]]) -> None:
    for temporary, _target, _change in prepared:
        temporary.unlink(missing_ok=True)
