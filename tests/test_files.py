from pathlib import PurePosixPath

from conftest import git_add, make_files

from devai.analyzer.files import list_project_files
from devai.models import FileSource


def names(listing):
    return [str(path) for path in listing.files]


# --- filesystem mode -------------------------------------------------------


def test_lists_files_recursively_as_sorted_posix_paths(tmp_path):
    make_files(tmp_path, "src/pkg/c.py", "a.py", "src/b.py")

    listing = list_project_files(tmp_path)

    assert listing.files == [
        PurePosixPath("a.py"),
        PurePosixPath("src/b.py"),
        PurePosixPath("src/pkg/c.py"),
    ]
    assert listing.source is FileSource.FILESYSTEM


def test_skips_default_ignored_directories(tmp_path):
    make_files(
        tmp_path,
        "main.py",
        "node_modules/lib/index.js",
        ".venv/bin/python",
        "src/__pycache__/main.cpython-314.pyc",
        ".pytest_cache/README.md",
        ".git/HEAD",
    )

    assert names(list_project_files(tmp_path)) == ["main.py"]


def test_applies_root_gitignore(tmp_path):
    make_files(
        tmp_path,
        ".gitignore",
        "app.js",
        "debug.log",
        "logs/today.txt",
        ".history/app_2026.js",
        ".vscode/settings.json",
        ".vscode/extensions.json",
    )
    (tmp_path / ".gitignore").write_text(
        "*.log\nlogs/\n.history/\n.vscode/*\n!.vscode/extensions.json\n"
    )

    listing = list_project_files(tmp_path)

    assert names(listing) == [".gitignore", ".vscode/extensions.json", "app.js"]
    assert listing.source is FileSource.FILESYSTEM_GITIGNORE


def test_anchored_gitignore_pattern_only_matches_at_root(tmp_path):
    make_files(tmp_path, ".gitignore", "out/a.txt", "src/out/b.txt")
    (tmp_path / ".gitignore").write_text("/out\n")

    assert names(list_project_files(tmp_path)) == [".gitignore", "src/out/b.txt"]


def test_does_not_follow_symlinked_directories(tmp_path):
    make_files(tmp_path, "real/a.py")
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)

    assert names(list_project_files(tmp_path)) == ["real/a.py"]


# --- git mode --------------------------------------------------------------


def test_git_mode_lists_untracked_and_skips_ignored(git_repo):
    make_files(git_repo, ".gitignore", "app.py", "secret.log", "build/out.bin")
    (git_repo / ".gitignore").write_text("*.log\nbuild/\n")

    listing = list_project_files(git_repo)

    assert listing.source is FileSource.GIT
    assert names(listing) == [".gitignore", "app.py"]


def test_git_mode_honors_nested_gitignore(git_repo):
    make_files(git_repo, "web/.gitignore", "web/index.js", "web/cache.tmp")
    (git_repo / "web" / ".gitignore").write_text("*.tmp\n")

    assert names(list_project_files(git_repo)) == ["web/.gitignore", "web/index.js"]


def test_git_mode_skips_tracked_files_deleted_from_disk(git_repo):
    make_files(git_repo, "keep.py", "gone.py")
    git_add(git_repo, "keep.py", "gone.py")
    (git_repo / "gone.py").unlink()

    assert names(list_project_files(git_repo)) == ["keep.py"]


def test_git_mode_in_subdirectory_lists_paths_relative_to_it(git_repo):
    make_files(git_repo, "README.md", "src/app.py", "src/lib/util.py")

    listing = list_project_files(git_repo / "src")

    assert listing.source is FileSource.GIT
    assert names(listing) == ["app.py", "lib/util.py"]


def test_handles_file_names_with_spaces_and_accents(git_repo):
    make_files(git_repo, "relatório final.md", "código.py")

    assert names(list_project_files(git_repo)) == ["código.py", "relatório final.md"]


def test_falls_back_to_filesystem_when_git_is_missing(git_repo, monkeypatch):
    make_files(git_repo, "app.py")
    monkeypatch.setenv("PATH", "")  # subprocess can no longer find git

    listing = list_project_files(git_repo)

    assert listing.source is FileSource.FILESYSTEM
    assert names(listing) == ["app.py"]
