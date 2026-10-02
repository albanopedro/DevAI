"""Pair source files with test files by name (D045).

A test file covers a source file when the source's name, as words, appears
in the test's name: "json_report.py" ↔ "test_json_report.py", "Cart.jsx" ↔
"Cart.test.jsx" or "__tests__/cart.js". Comparing words, not substrings,
keeps "app.py" from being covered by "test_apply.py".
"""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from devai.analyzer.config_files import is_config_file
from devai.analyzer.languages import language_for
from devai.analyzer.testing import is_test_file

CHECKED_LANGUAGES = frozenset({"Python", "JavaScript", "TypeScript"})
# Entry points and glue code that rarely get a test of their own.
EXCLUDED_NAMES = frozenset(
    {"__init__.py", "__main__.py", "conftest.py", "setup.py", "manage.py"}
)
WORD = re.compile(r"[a-z0-9]+")


def source_files(files: Iterable[PurePosixPath]) -> list[PurePosixPath]:
    """Source files whose tests are worth looking for."""
    return [
        path
        for path in files
        if language_for(path) in CHECKED_LANGUAGES
        and not is_test_file(path)
        and not is_config_file(path)
        and path.name not in EXCLUDED_NAMES
        and not path.name.endswith(".d.ts")  # TypeScript type declarations
    ]


def test_files(files: Iterable[PurePosixPath]) -> list[PurePosixPath]:
    return [path for path in files if is_test_file(path)]


def words(path: PurePosixPath) -> list[str]:
    """The words of a file name without extensions: "Cart.test.jsx" → [cart, test]."""
    return WORD.findall(path.name.split(".")[0].lower() + " " + middle(path))


def middle(path: PurePosixPath) -> str:
    """Name parts between the stem and the extension ("test" in "Cart.test.jsx")."""
    parts = path.name.lower().split(".")
    return " ".join(parts[1:-1])


def covers(test: PurePosixPath, source: PurePosixPath) -> bool:
    """True if `source`'s name words appear, in order and together, in `test`'s."""
    wanted = WORD.findall(source.name.split(".")[0].lower())
    found = words(test)
    if not wanted:
        return False
    return any(
        found[start : start + len(wanted)] == wanted
        for start in range(len(found) - len(wanted) + 1)
    )


def without_tests(
    sources: list[PurePosixPath], tests: list[PurePosixPath]
) -> list[PurePosixPath]:
    """Sources that no test file covers, by name."""
    return [source for source in sources if not any(covers(t, source) for t in tests)]
