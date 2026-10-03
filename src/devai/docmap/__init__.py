"""`devai docs`: where documentation seems to be missing (D048).

Nothing is sent anywhere and nothing is executed. Files are read only as the
analyzer allows (the project's ignore rules and D021). Test files are left
out: tests document themselves through their names.
"""

from dataclasses import dataclass
from pathlib import PurePosixPath

from devai.analyzer.config_files import is_config_file
from devai.analyzer.languages import language_for
from devai.analyzer.testing import is_test_file
from devai.checks.secrets import read_scannable_text
from devai.docmap.js_docs import js_names
from devai.docmap.python_docs import MODULE, NotPython, python_names
from devai.docmap.readme import ReadmeMap, check_readme
from devai.models import ProjectInfo

__all__ = ["MODULE", "DocsMap", "ReadmeMap", "build_docs_map", "doc_sources"]

CHECKED_LANGUAGES = frozenset({"Python", "JavaScript", "TypeScript"})
# Glue code that rarely needs documentation of its own.
EXCLUDED_NAMES = frozenset({"conftest.py", "setup.py", "manage.py"})


@dataclass(frozen=True)
class DocsMap:
    """An estimate of where docs are missing; README scripts are facts."""

    sources_checked: int
    languages: tuple[str, ...]
    public_names: int
    documented: int
    # File → names without docs; MODULE stands for a Python module docstring.
    undocumented: tuple[tuple[PurePosixPath, tuple[str, ...]], ...]
    not_parsed: tuple[PurePosixPath, ...]  # .py files with invalid syntax
    readme: ReadmeMap | None  # None: no README at the root


def doc_sources(files: tuple[PurePosixPath, ...]) -> list[PurePosixPath]:
    """Source files whose public names are worth documenting."""
    return [
        path
        for path in files
        if language_for(path) in CHECKED_LANGUAGES
        and not is_test_file(path)
        and not is_config_file(path)
        and path.name not in EXCLUDED_NAMES
        and path.suffix != ".pyi"  # type stubs
        and not path.name.endswith(".d.ts")
        and not is_private(path)
    ]


def is_private(path: PurePosixPath) -> bool:
    """`_internal.py` or `_vendor/x.py` (but not `__init__.py`): not public API."""
    parts = (*path.parts[:-1], path.name.split(".")[0])
    return any(part.startswith("_") and not part.startswith("__") for part in parts)


def build_docs_map(info: ProjectInfo) -> DocsMap:
    sources = doc_sources(info.files)
    public_names = 0
    documented = 0
    undocumented = []
    not_parsed = []
    for path in sources:
        text = read_scannable_text(info.path / path, path)
        if text is None:
            continue
        try:
            names = python_names(text) if path.suffix == ".py" else js_names(text)
        except NotPython:
            not_parsed.append(path)
            continue
        public_names += len(names)
        documented += sum(has_docs for _, has_docs in names)
        missing = tuple(name for name, has_docs in names if not has_docs)
        if missing:
            undocumented.append((path, missing))

    return DocsMap(
        sources_checked=len(sources),
        languages=tuple(sorted({language_for(path) for path in sources})),
        public_names=public_names,
        documented=documented,
        undocumented=tuple(
            sorted(undocumented, key=lambda item: (-len(item[1]), str(item[0])))
        ),
        not_parsed=tuple(not_parsed),
        readme=check_readme(info.path, info.files),
    )
