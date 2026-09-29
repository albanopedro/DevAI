"""Summarize how files are spread across top-level directories."""

from collections import Counter
from collections.abc import Iterable
from pathlib import PurePosixPath

from devai.models import DirectoryStat


def summarize_structure(
    files: Iterable[PurePosixPath],
) -> tuple[tuple[DirectoryStat, ...], int]:
    """Return (top-level directories sorted by name, files at the root)."""
    directory_counts: Counter[str] = Counter()
    root_files = 0
    for path in files:
        if len(path.parts) == 1:
            root_files += 1
        else:
            directory_counts[path.parts[0]] += 1

    directories = tuple(
        DirectoryStat(name, total) for name, total in sorted(directory_counts.items())
    )
    return directories, root_files
