from pathlib import Path

import pytest

from devai.scanner import scan_project


def make_files(root: Path, *relative_paths: str) -> None:
    for relative in relative_paths:
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("x")


def test_counts_files_recursively(tmp_path):
    make_files(tmp_path, "a.py", "src/b.py", "src/pkg/c.py")

    info = scan_project(tmp_path)

    assert info.file_count == 3


def test_skips_ignored_directories(tmp_path):
    make_files(
        tmp_path,
        "main.py",
        "node_modules/lib/index.js",
        ".venv/bin/python",
        "src/__pycache__/main.cpython-314.pyc",
        ".git/HEAD",
    )

    info = scan_project(tmp_path)

    assert info.file_count == 1


def test_uses_directory_name_as_project_name(tmp_path):
    project = tmp_path / "my-project"
    project.mkdir()

    assert scan_project(project).name == "my-project"


def test_detects_git_repository(tmp_path):
    (tmp_path / ".git").mkdir()

    assert scan_project(tmp_path).has_git is True


def test_no_git_repository(tmp_path):
    assert scan_project(tmp_path).has_git is False


@pytest.mark.parametrize(
    "filename", ["README.md", "readme.rst", "Readme", "README.txt"]
)
def test_detects_readme_variants(tmp_path, filename):
    make_files(tmp_path, filename)

    assert scan_project(tmp_path).has_readme is True


def test_readme_in_subdirectory_does_not_count(tmp_path):
    make_files(tmp_path, "docs/README.md")

    assert scan_project(tmp_path).has_readme is False


def test_does_not_follow_symlinked_directories(tmp_path):
    make_files(tmp_path, "real/a.py")
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)

    assert scan_project(tmp_path).file_count == 1


def test_rejects_missing_path(tmp_path):
    with pytest.raises(NotADirectoryError):
        scan_project(tmp_path / "missing")


def test_rejects_file_path(tmp_path):
    make_files(tmp_path, "file.txt")

    with pytest.raises(NotADirectoryError):
        scan_project(tmp_path / "file.txt")
