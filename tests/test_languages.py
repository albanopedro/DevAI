from pathlib import PurePosixPath

from devai.analyzer.languages import detect_languages, language_for
from devai.models import LanguageStat


def paths(*names):
    return [PurePosixPath(name) for name in names]


def test_maps_common_extensions():
    assert language_for(PurePosixPath("app.py")) == "Python"
    assert language_for(PurePosixPath("App.tsx")) == "TypeScript"
    assert language_for(PurePosixPath("App.jsx")) == "JavaScript"
    assert language_for(PurePosixPath("styles/main.css")) == "CSS"


def test_extension_matching_is_case_insensitive():
    assert language_for(PurePosixPath("LEGACY.PY")) == "Python"


def test_ignores_data_docs_and_unknown_files():
    for name in ["README.md", "package.json", "config.yaml", "logo.png", "Makefile"]:
        assert language_for(PurePosixPath(name)) is None


def test_counts_and_ranks_languages():
    files = paths("a.py", "b.py", "c.js", "d.jsx", "e.ts", "f.py", "README.md")

    assert detect_languages(files) == (
        LanguageStat("Python", 3),
        LanguageStat("JavaScript", 2),
        LanguageStat("TypeScript", 1),
    )


def test_ties_are_sorted_by_name():
    assert detect_languages(paths("a.go", "b.css")) == (
        LanguageStat("CSS", 1),
        LanguageStat("Go", 1),
    )


def test_no_languages():
    assert detect_languages(paths("README.md", "data.json")) == ()
