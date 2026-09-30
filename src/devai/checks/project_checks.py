"""Project-level checks: README, .gitignore, tests and exposed .env files."""

from collections.abc import Callable
from pathlib import Path

from devai.checks.result import CheckResult, failing, passing
from devai.checks.secrets import is_real_env_file
from devai.models import Finding, ProjectInfo, Severity


def check_readme(info: ProjectInfo) -> CheckResult:
    if info.has_readme:
        return passing("README found")
    return failing(
        Finding("no-readme", Severity.LOW, "No README found at the project root")
    )


def check_gitignore(info: ProjectInfo) -> CheckResult:
    if has_gitignore(info.path, search_parents=info.has_git):
        return passing(".gitignore found")
    return failing(Finding("no-gitignore", Severity.LOW, "No .gitignore found"))


def check_tests(info: ProjectInfo) -> CheckResult:
    if info.tests.files:
        noun = "file" if info.tests.files == 1 else "files"
        return passing(f"Tests found ({info.tests.files} {noun})")
    if not info.languages:
        return CheckResult()  # no source code: nothing to test
    return failing(Finding("no-tests", Severity.MEDIUM, "No automated tests detected"))


def check_env_files(info: ProjectInfo) -> CheckResult:
    exposed = [path for path in info.files if is_real_env_file(path)]
    if not exposed:
        return passing("No exposed .env files")

    message = (
        "Environment file is tracked or not ignored by git"
        if info.has_git
        else "Environment file is not covered by .gitignore"
    )
    return failing(
        *(
            Finding("env-not-ignored", Severity.HIGH, message, file=path)
            for path in exposed
        )
    )


def has_gitignore(root: Path, search_parents: bool) -> bool:
    """Look for .gitignore in `root`; inside a repo, also up to the repo root."""
    directories = [root, *root.parents] if search_parents else [root]
    for directory in directories:
        if (directory / ".gitignore").is_file():
            return True
        if (directory / ".git").exists():
            return False  # reached the repository root
    return False


PROJECT_CHECKS: tuple[Callable[[ProjectInfo], CheckResult], ...] = (
    check_readme,
    check_gitignore,
    check_tests,
    check_env_files,
)
