from pathlib import PurePosixPath

from devai.analyzer.structure import summarize_structure
from devai.models import DirectoryStat


def test_counts_files_per_top_level_directory():
    files = [
        PurePosixPath(name)
        for name in ["src/a.py", "src/pkg/b.py", "tests/test_a.py", "README.md"]
    ]

    directories, root_files = summarize_structure(files)

    assert directories == (DirectoryStat("src", 2), DirectoryStat("tests", 1))
    assert root_files == 1


def test_directories_are_sorted_by_name():
    files = [PurePosixPath("zeta/a"), PurePosixPath(".github/ci.yml")]

    directories, _ = summarize_structure(files)

    assert [directory.name for directory in directories] == [".github", "zeta"]


def test_empty_project():
    assert summarize_structure([]) == ((), 0)
