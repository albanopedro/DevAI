from pathlib import PurePosixPath

import pytest

from devai.analyzer.testing import detect_tests, is_test_file
from devai.models import Dependency, Ecosystem, Manifest, TestSummary


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_api.py",
        "tests/conftest.py",
        "backend/test/helpers.py",
        "src/__tests__/App.jsx",
        "test_models.py",
        "models_test.py",
        "server/handler_test.go",
        "src/App.test.jsx",
        "src/api.spec.ts",
        "lib/utils.test.mjs",
    ],
)
def test_recognizes_test_files(path):
    assert is_test_file(PurePosixPath(path)) is True


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",
        "src/testing_utils.py",
        "src/contest.js",
        "tests/fixtures/data.json",  # fixtures are not source code
        "tests/README.md",
        "docs/test-plan.md",
    ],
)
def test_ignores_non_test_files(path):
    assert is_test_file(PurePosixPath(path)) is False


def test_summary_counts_files_and_frameworks():
    files = [PurePosixPath(p) for p in ["tests/test_a.py", "tests/test_b.py", "a.py"]]
    manifests = [
        Manifest(
            PurePosixPath("pyproject.toml"),
            Ecosystem.PYTHON,
            (Dependency("pytest", dev=True),),
        )
    ]

    assert detect_tests(files, manifests) == TestSummary(2, ("pytest",))


def test_summary_without_tests():
    assert detect_tests([PurePosixPath("main.py")], []) == TestSummary(0, ())
