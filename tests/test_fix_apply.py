import os
import stat
from pathlib import PurePosixPath

import pytest
from conftest import git_commit, git_run, write

from devai.chat.retrieval import SelectedFile
from devai.fix import apply as apply_module
from devai.fix.apply import ApplyError, WriteError, apply_changes, check_can_apply
from devai.fix.edits import FileChange, unified_diff


def change(path, before, after):
    return FileChange(
        PurePosixPath(path),
        before,
        after,
        unified_diff(PurePosixPath(path), before, after),
    )


def selected(repo, path):
    return SelectedFile(PurePosixPath(path), "named", (repo / path).read_text())


@pytest.fixture
def repo(git_repo):
    write(git_repo, "a.py", "a = 1\n")
    write(git_repo, "b.py", "b = 1\n")
    git_commit(git_repo, "fixture")
    return git_repo


# --- before the AI call ---------------------------------------------------------------


def test_clean_tracked_files_can_be_fixed(repo):
    check_can_apply(repo, [selected(repo, "a.py"), selected(repo, "b.py")])


def test_staged_changes_also_block(repo):
    write(repo, "a.py", "a = 2\n")
    git_run(repo, "add", "a.py")  # staged, not committed

    with pytest.raises(ApplyError, match="uncommitted changes"):
        check_can_apply(repo, [selected(repo, "a.py")])


def test_non_utf8_file_is_refused(repo):
    (repo / "latin.txt").write_bytes("café\n".encode("latin-1"))
    git_commit(repo, "latin-1 file")
    item = SelectedFile(PurePosixPath("latin.txt"), "named", "caf�\n")

    with pytest.raises(ApplyError, match="isn't valid UTF-8"):
        check_can_apply(repo, [item])


# --- writing --------------------------------------------------------------------


def test_permissions_and_crlf_are_preserved(repo):
    write(repo, "run.sh", "echo one\r\n")
    (repo / "run.sh").chmod(0o755)
    git_commit(repo, "script")

    apply_changes(repo, [change("run.sh", "echo one\r\n", "echo two\r\n")])

    assert (repo / "run.sh").read_bytes() == b"echo two\r\n"
    assert stat.S_IMODE((repo / "run.sh").stat().st_mode) == 0o755


def test_no_temporary_files_are_left_behind(repo):
    apply_changes(repo, [change("a.py", "a = 1\n", "a = 2\n")])

    assert not list(repo.glob(".*.devai-tmp"))


def test_all_or_nothing_when_the_second_write_fails(repo, monkeypatch):
    real_replace = os.replace
    calls = []

    def failing_replace(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError("disk full")
        real_replace(source, target)

    monkeypatch.setattr(apply_module.os, "replace", failing_replace)
    changes = [
        change("a.py", "a = 1\n", "a = 2\n"),
        change("b.py", "b = 1\n", "b = 2\n"),
    ]

    with pytest.raises(WriteError, match="already written were restored"):
        apply_changes(repo, changes)

    assert (repo / "a.py").read_text() == "a = 1\n"  # rolled back
    assert (repo / "b.py").read_text() == "b = 1\n"  # never written
    assert not list(repo.glob(".*.devai-tmp"))


def test_changed_file_is_not_overwritten(repo):
    write(repo, "a.py", "a = 1  # edited\n")

    with pytest.raises(ApplyError, match="changed after the fix was proposed"):
        apply_changes(repo, [change("a.py", "a = 1\n", "a = 2\n")])

    assert (repo / "a.py").read_text() == "a = 1  # edited\n"
