from pathlib import PurePosixPath

import pytest
from conftest import write

from devai.analyzer import analyze_project
from devai.testmap import build_coverage_map
from devai.testmap.pairing import covers, source_files, without_tests
from devai.testmap.symbols import NotPython, public_symbols, unmentioned


def paths(*names):
    return [PurePosixPath(name) for name in names]


# --- pairing by name ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("test", "source"),
    [
        ("tests/test_report.py", "src/devai/report.py"),
        ("tests/report_test.py", "src/devai/report.py"),
        ("tests/test_json_report.py", "src/devai/json_report.py"),
        ("src/Cart.test.jsx", "src/Cart.jsx"),
        ("src/api.spec.ts", "src/api.ts"),
        ("src/__tests__/cart.js", "src/cart.js"),
        ("x/userService.test.ts", "x/userService.ts"),
    ],
)
def test_names_that_pair(test, source):
    assert covers(PurePosixPath(test), PurePosixPath(source)) is True


@pytest.mark.parametrize(
    ("test", "source"),
    [
        ("tests/test_apply.py", "src/app.py"),  # "app" isn't the word "apply"
        ("tests/test_report.py", "src/json_report.py"),  # only part of the name
        ("tests/test_cart.py", "src/carts.py"),
    ],
)
def test_names_that_do_not_pair(test, source):
    assert covers(PurePosixPath(test), PurePosixPath(source)) is False


def test_only_relevant_source_files_are_checked():
    files = paths(
        "src/app.py",
        "src/__init__.py",
        "src/__main__.py",
        "tests/conftest.py",
        "tests/test_app.py",
        "vite.config.js",
        "src/types.d.ts",
        "README.md",
        "src/main.go",
        "src/App.jsx",
    )

    assert [str(p) for p in source_files(files)] == ["src/app.py", "src/App.jsx"]


def test_without_tests():
    sources = paths("src/app.py", "src/cart.js")
    tests = paths("tests/test_app.py")

    assert without_tests(sources, tests) == paths("src/cart.js")


# --- Python symbols -------------------------------------------------------------------


def test_public_top_level_functions_and_classes():
    code = (
        "import os\n"
        "def run(): pass\n"
        "async def fetch(): pass\n"
        "class Cart:\n"
        "    def add(self): pass\n"  # a method: not top-level
        "def _helper(): pass\n"
        "VALUE = 1\n"
    )

    assert public_symbols(code) == ["run", "fetch", "Cart"]


def test_invalid_python_raises():
    with pytest.raises(NotPython):
        public_symbols("def broken(:\n")


def test_unmentioned_matches_whole_words_only():
    tests_text = "from app import run\nassert cart_total() == 3\n"

    assert unmentioned(["run", "cart", "total", "cart_total"], tests_text) == [
        "cart",
        "total",
    ]


# --- the map --------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path):
    write(tmp_path, "src/app.py", "def run():\n    pass\n\n\ndef stop():\n    pass\n")
    write(tmp_path, "src/cart.py", "class Cart:\n    pass\n")
    write(tmp_path, "src/broken.py", "def broken(:\n")
    write(
        tmp_path,
        "tests/test_app.py",
        "from app import run\n\n\ndef test_run():\n    run()\n",
    )
    return tmp_path


def test_coverage_map(project):
    coverage = build_coverage_map(analyze_project(project))

    assert coverage.test_files == 1
    assert coverage.sources_checked == 3
    assert coverage.languages == ("Python",)
    assert [str(p) for p in coverage.without_tests] == ["src/broken.py", "src/cart.py"]
    assert {str(p): s for p, s in coverage.untested_symbols} == {
        "src/app.py": ("stop",),
        "src/cart.py": ("Cart",),
    }
    assert [str(p) for p in coverage.not_parsed] == ["src/broken.py"]


def test_ignored_files_are_not_read(project):
    write(project, ".gitignore", "generated/\n")
    write(project, "generated/test_cart.py", "Cart  # would 'cover' cart.py\n")

    coverage = build_coverage_map(analyze_project(project))

    assert "src/cart.py" in [str(p) for p in coverage.without_tests]
