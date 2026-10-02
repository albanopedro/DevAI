"""`devai test`: where tests seem to be missing, from names alone (D045).

Nothing is executed: no tests, no project code. Files are read only as the
analyzer allows (the project's ignore rules and D021).
"""

from dataclasses import dataclass
from pathlib import PurePosixPath

from devai.analyzer.languages import language_for
from devai.checks.secrets import read_scannable_text
from devai.models import ProjectInfo
from devai.testmap.pairing import source_files, test_files, without_tests
from devai.testmap.symbols import NotPython, public_symbols, unmentioned


@dataclass(frozen=True)
class CoverageMap:
    """An estimate of where tests are missing (not a coverage measurement)."""

    test_files: int
    frameworks: tuple[str, ...]
    sources_checked: int
    languages: tuple[str, ...]
    without_tests: tuple[PurePosixPath, ...]
    # Python files → public functions/classes no test mentions by name.
    untested_symbols: tuple[tuple[PurePosixPath, tuple[str, ...]], ...]
    not_parsed: tuple[PurePosixPath, ...]  # .py files with invalid syntax


def build_coverage_map(info: ProjectInfo) -> CoverageMap:
    sources = source_files(info.files)
    tests = test_files(info.files)

    tests_text = "\n".join(
        text
        for path in tests
        if (text := read_scannable_text(info.path / path, path)) is not None
    )
    untested = []
    not_parsed = []
    for path in sources:
        if path.suffix != ".py":
            continue  # symbols only for Python (it has a parser in the stdlib)
        text = read_scannable_text(info.path / path, path)
        if text is None:
            continue
        try:
            missing = unmentioned(public_symbols(text), tests_text)
        except NotPython:
            not_parsed.append(path)
            continue
        if missing:
            untested.append((path, tuple(missing)))

    return CoverageMap(
        test_files=len(tests),
        frameworks=info.tests.frameworks,
        sources_checked=len(sources),
        languages=tuple(sorted({language_for(path) for path in sources})),
        without_tests=tuple(without_tests(sources, tests)),
        untested_symbols=tuple(
            sorted(untested, key=lambda item: (-len(item[1]), str(item[0])))
        ),
        not_parsed=tuple(not_parsed),
    )
