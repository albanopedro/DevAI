"""`devai review`: checks on the current git changes, and the AI review context."""

from pathlib import Path

from devai.models import CheckReport, ReviewReport
from devai.review.checks import run_review_checks
from devai.review.diff import Changes, ReviewError, collect_changes

__all__ = [
    "Changes",
    "ReviewError",
    "collect_changes",
    "review_changes",
    "review_report",
    "run_review_checks",
]


def review_report(changes: Changes, checks: CheckReport) -> ReviewReport:
    return ReviewReport(
        name=changes.root.name,
        path=changes.root,
        description=changes.description,
        files=changes.files,
        checks=checks,
    )


def review_changes(
    path: Path, staged: bool = False, base: str | None = None
) -> ReviewReport:
    changes = collect_changes(path, staged=staged, base=base)
    return review_report(changes, run_review_checks(changes))
