import pytest
from conftest import write

from devai import git


def test_is_ignored_answers_for_paths_that_do_not_exist_yet(git_repo):
    write(git_repo, ".gitignore", "generated/\n")

    assert git.is_ignored(git_repo, "generated/test_new.py") is True
    assert git.is_ignored(git_repo, "tests/test_new.py") is False


def test_is_ignored_raises_instead_of_answering_no(tmp_path):
    # Outside a repository git exits with an error (128). Reading that as
    # "not ignored" would make callers fail open; it must raise instead.
    with pytest.raises(git.GitError):
        git.is_ignored(tmp_path, "anything.py")
