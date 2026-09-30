"""`devai review`: local checks on the current git changes (no AI, no network)."""

from pathlib import Path

from devai.models import ReviewReport
from devai.review.checks import run_review_checks
from devai.review.diff import ReviewError, collect_changes

__all__ = ["ReviewError", "review_changes"]


def review_changes(
    path: Path, staged: bool = False, base: str | None = None
) -> ReviewReport:
    changes = collect_changes(path, staged=staged, base=base)
    return ReviewReport(
        name=changes.root.name,
        path=changes.root,
        description=changes.description,
        files=changes.files,
        checks=run_review_checks(changes),
    )
