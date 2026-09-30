from pathlib import PurePosixPath

import pytest
from conftest import FAKE_SECRETS, git_commit, git_run, write

from devai import git
from devai.review.diff import (
    AddedLine,
    ReviewError,
    collect_changes,
    parse_added_lines,
    parse_name_status,
    parse_numstat,
)


def by_path(changes):
    return {str(file.path): file for file in changes.files}


def lines_of(changes, path):
    return changes.added_lines[PurePosixPath(path)]


@pytest.fixture
def repo(git_repo):
    write(git_repo, "app.py", "a\nb\nc\nd\n")
    write(git_repo, "old.txt", "x\ny\nz\n")
    write(git_repo, "gone.txt", "remove me\n")
    git_commit(git_repo, "initial")
    return git_repo


# --- parsing git's output (formats checked against real git) ----------------


def test_parse_name_status_with_rename():
    output = "D\0gone.txt\0M\0app.py\0R100\0old.txt\0new náme.txt\0"

    assert parse_name_status(output) == [
        ("D", None, PurePosixPath("gone.txt")),
        ("M", None, PurePosixPath("app.py")),
        ("R", PurePosixPath("old.txt"), PurePosixPath("new náme.txt")),
    ]


def test_parse_numstat_with_binary_and_rename():
    # "\0".join, not adjacent literals: "\0" + "0" would read as the escape "\00".
    output = "\0".join(
        ["0\t1\tgone.txt", "-\t-\timg.png", "0\t0\t", "old.txt", "new.txt", ""]
    )

    assert parse_numstat(output) == {
        PurePosixPath("gone.txt"): (0, 1),
        PurePosixPath("img.png"): (None, None),
        PurePosixPath("new.txt"): (0, 0),
    }


def test_parse_added_lines_numbers_lines_in_the_new_file():
    patch = (
        "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n"
        "@@ -2,0 +3,2 @@ b\n+NEW1\n+NEW2\n@@ -4 +5,0 @@ c\n-d\n"
    )

    assert parse_added_lines(patch) == (AddedLine(3, "NEW1"), AddedLine(4, "NEW2"))


def test_form_feed_inside_a_line_does_not_shift_numbers():
    patch = "@@ -0,0 +1,2 @@\n+page\x0cbreak\n+second\n"

    assert [line.number for line in parse_added_lines(patch)] == [1, 2]


# --- collecting changes from a real (throwaway) repository ------------------


def test_clean_repository_has_no_changes(repo):
    assert collect_changes(repo).files == ()


def test_modified_file_reports_only_added_lines(repo):
    write(repo, "app.py", "a\nb\nNEW1\nNEW2\nc\n")  # 2 added, "d" removed

    changes = collect_changes(repo)

    app = by_path(changes)["app.py"]
    assert (app.status, app.additions, app.deletions) == ("M", 2, 1)
    assert lines_of(changes, "app.py") == (AddedLine(3, "NEW1"), AddedLine(4, "NEW2"))


def test_default_mode_includes_staged_unstaged_and_untracked(repo):
    write(repo, "staged.py", "print(1)\n")
    git_run(repo, "add", "staged.py")
    write(repo, "app.py", "a\nb\nc\nd\ne\n")  # unstaged
    write(repo, "notes/new file.md", "one\ntwo\n")  # untracked, with a space

    files = by_path(collect_changes(repo))

    assert files["staged.py"].status == "A"
    assert files["app.py"].status == "M"
    untracked = files["notes/new file.md"]
    assert (untracked.status, untracked.untracked, untracked.additions) == (
        "A",
        True,
        2,
    )


def test_staged_mode_is_what_the_next_commit_contains(repo):
    write(repo, "staged.py", "print(1)\n")
    git_run(repo, "add", "staged.py")
    write(repo, "app.py", "changed but not staged\n")
    write(repo, "untracked.py", "x = 1\n")

    changes = collect_changes(repo, staged=True)

    assert list(by_path(changes)) == ["staged.py"]
    assert "staged changes" in changes.description


def test_base_mode_is_like_a_pull_request(repo):
    git_run(repo, "branch", "base")
    write(repo, "feature.py", "def feature():\n    return 1\n")
    git_commit(repo, "add feature")
    write(repo, "wip.py", "not committed yet\n")

    changes = collect_changes(repo, base="base")

    assert list(by_path(changes)) == ["feature.py"]  # uncommitted work excluded
    assert changes.description.startswith("committed changes since base (")


def test_unknown_base_is_a_clear_error(repo):
    with pytest.raises(ReviewError, match="Can't compare with 'nope'"):
        collect_changes(repo, base="nope")


def test_deleted_and_renamed_files(repo):
    git_run(repo, "rm", "-q", "gone.txt")
    git_run(repo, "mv", "old.txt", "renamed é.txt")

    files = by_path(collect_changes(repo))

    assert files["gone.txt"].status == "D"
    renamed = files["renamed é.txt"]
    assert (renamed.status, renamed.old_path) == ("R", PurePosixPath("old.txt"))


def test_binary_file_is_listed_but_not_read(repo):
    (repo / "logo.png").write_bytes(b"\x89PNG\0binary")
    git_run(repo, "add", "logo.png")

    changes = collect_changes(repo)

    assert by_path(changes)["logo.png"].additions is None
    assert PurePosixPath("logo.png") in changes.skipped
    assert PurePosixPath("logo.png") not in changes.added_lines


def test_env_file_content_is_never_read(repo, monkeypatch):
    secret, _ = FAKE_SECRETS["secret/openai-key"]
    write(repo, ".env", "OLD=1\n")
    git_commit(repo, "oops, committed .env")
    write(repo, ".env", f"OPENAI_API_KEY={secret}\n")
    write(repo, "config/.env.local", f"KEY={secret}\n")  # untracked

    calls = []
    original = git.run_git

    def spy(path, *args):
        calls.append(args)
        return original(path, *args)

    monkeypatch.setattr(git, "run_git", spy)
    changes = collect_changes(repo)

    assert {".env", "config/.env.local"} <= set(by_path(changes))
    assert all(".env" not in str(path) for path in changes.added_lines)
    content_diffs = [args for args in calls if "-U0" in args]
    assert not any(".env" in " ".join(args) for args in content_diffs)


def test_repository_without_commits(git_repo):
    write(git_repo, "first.py", "print('hello')\n")
    git_run(git_repo, "add", "first.py")
    write(git_repo, "draft.md", "notes\n")

    files = by_path(collect_changes(git_repo))

    assert files["first.py"].status == "A"
    assert files["draft.md"].untracked is True


def test_subdirectory_limits_and_relativizes_paths(repo):
    write(repo, "api/handler.py", "x = 1\n")
    write(repo, "web/app.js", "let y = 2\n")

    changes = collect_changes(repo / "api")

    assert list(by_path(changes)) == ["handler.py"]


def test_outside_a_git_repository(tmp_path):
    with pytest.raises(ReviewError, match="needs a git repository"):
        collect_changes(tmp_path)


def test_path_must_be_a_directory(tmp_path):
    with pytest.raises(NotADirectoryError):
        collect_changes(tmp_path / "missing")
