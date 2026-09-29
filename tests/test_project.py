import pytest
from conftest import make_files

from devai.analyzer import analyze_project
from devai.models import DirectoryStat, FileSource, LanguageStat


def test_builds_project_info(tmp_path):
    project = tmp_path / "my-project"
    make_files(project, "README.md", "src/app.py", "src/util.py", "web/index.js")

    info = analyze_project(project)

    assert info.name == "my-project"
    assert info.path == project.resolve()
    assert info.file_count == 4
    assert info.file_source is FileSource.FILESYSTEM
    assert info.has_git is False
    assert info.has_readme is True
    assert info.languages == (LanguageStat("Python", 2), LanguageStat("JavaScript", 1))
    assert info.directories == (DirectoryStat("src", 2), DirectoryStat("web", 1))
    assert info.root_file_count == 1
    assert info.warnings == ()


def test_detects_git_repository(git_repo):
    assert analyze_project(git_repo).has_git is True


def test_detects_git_from_a_subdirectory(git_repo):
    make_files(git_repo, "src/app.py")

    assert analyze_project(git_repo / "src").has_git is True


def test_warns_when_git_directory_is_unreadable(tmp_path):
    (tmp_path / ".git").mkdir()  # empty .git: git can't use it

    info = analyze_project(tmp_path)

    assert info.has_git is False
    assert len(info.warnings) == 1
    assert ".git directory exists" in info.warnings[0]


@pytest.mark.parametrize(
    "filename", ["README.md", "readme.rst", "Readme", "README.txt"]
)
def test_detects_readme_variants(tmp_path, filename):
    make_files(tmp_path, filename)

    assert analyze_project(tmp_path).has_readme is True


def test_readme_in_subdirectory_does_not_count(tmp_path):
    make_files(tmp_path, "docs/README.md")

    assert analyze_project(tmp_path).has_readme is False


def test_rejects_missing_path(tmp_path):
    with pytest.raises(NotADirectoryError):
        analyze_project(tmp_path / "missing")


def test_rejects_file_path(tmp_path):
    make_files(tmp_path, "file.txt")

    with pytest.raises(NotADirectoryError):
        analyze_project(tmp_path / "file.txt")
