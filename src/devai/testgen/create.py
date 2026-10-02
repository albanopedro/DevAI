"""Create a validated test file, never overwriting anything (D047).

The content goes to a temporary file in the target directory, then os.link
creates the target from it. Linking fails if the target exists, so even a
file that appears at the last moment is never overwritten. Missing parent
directories are created and reported, so the undo command can remove them.
DevAI never runs the tests it creates.
"""

import os
import shlex
import tempfile
from pathlib import Path, PurePosixPath


class CreateError(Exception):
    """The file couldn't be created; nothing was left behind."""


def create_test_file(
    root: Path, path: PurePosixPath, content: str
) -> list[PurePosixPath]:
    """Create root/path with `content`. Returns the directories it had to create."""
    target = root / path
    created = missing_directories(root, path)
    for directory in created:
        (root / directory).mkdir()

    descriptor, name = tempfile.mkstemp(dir=target.parent, suffix=".devai-tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.link(temporary, target)  # fails if the target exists: no overwrite
    except FileExistsError:
        temporary.unlink(missing_ok=True)  # before rmdir: directories must be empty
        remove_directories(root, created)
        raise CreateError(f"{path} appeared meanwhile; nothing was written") from None
    except OSError as error:
        temporary.unlink(missing_ok=True)
        remove_directories(root, created)
        raise CreateError(f"couldn't create {path} ({error})") from error
    temporary.unlink()  # the link keeps the content under the target's name
    return created


def missing_directories(root: Path, path: PurePosixPath) -> list[PurePosixPath]:
    """Parent directories of `path` that don't exist yet, outermost first."""
    missing = []
    for parent in reversed(path.parents[:-1]):  # skip "." (the project root)
        if not (root / parent).exists():
            missing.append(parent)
    return missing


def remove_directories(root: Path, directories: list[PurePosixPath]) -> None:
    for directory in reversed(directories):
        try:
            (root / directory).rmdir()  # only if still empty
        except OSError:
            pass


def undo_command(path: PurePosixPath, created: list[PurePosixPath]) -> str:
    command = f"rm {shlex.quote(str(path))}"
    for directory in reversed(created):  # innermost first
        command += f" && rmdir {shlex.quote(str(directory))}"
    return command


RUNNERS = {
    "pytest": "pytest {path}",
    "Jest": "npx jest {path}",
    "Vitest": "npx vitest run {path}",
    "Mocha": "npx mocha {path}",
}


def run_command(frameworks: list[str] | tuple[str, ...], path: PurePosixPath) -> str:
    """How YOU can run the new tests. Built by DevAI, never copied from the AI."""
    quoted = shlex.quote(str(path))
    for framework in frameworks:
        if framework in RUNNERS:
            return RUNNERS[framework].format(path=quoted)
    if path.suffix == ".py":
        return f"pytest {quoted}  (install pytest first if needed)"
    return f"run {quoted} with your project's test runner"
