"""Detect automated tests: test files by convention, test frameworks by deps."""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from devai.analyzer.frameworks import detect_test_frameworks
from devai.analyzer.languages import language_for
from devai.models import Manifest, TestSummary

TEST_DIRECTORIES = frozenset({"tests", "test", "__tests__"})

# test_x.py, x_test.py, x_test.go, x.test.js, x.spec.tsx, ...
TEST_FILE_NAME = re.compile(
    r"test_.*\.py|.*_test\.(py|go)|.*\.(test|spec)\.[cm]?[jt]sx?", re.IGNORECASE
)


def detect_tests(
    files: Iterable[PurePosixPath], manifests: Iterable[Manifest]
) -> TestSummary:
    return TestSummary(
        files=sum(1 for path in files if is_test_file(path)),
        frameworks=detect_test_frameworks(manifests),
    )


def is_test_file(path: PurePosixPath) -> bool:
    """True for source files named like tests or placed in a test directory.

    Only source code counts: fixtures such as JSON or images inside tests/
    are not test files.
    """
    if language_for(path) is None:
        return False
    if any(part.lower() in TEST_DIRECTORIES for part in path.parts[:-1]):
        return True
    return TEST_FILE_NAME.fullmatch(path.name) is not None
