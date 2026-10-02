import os
from pathlib import PurePosixPath

import pytest
from conftest import write

from devai.testgen import create as create_module
from devai.testgen.create import CreateError, create_test_file, undo_command


def test_creates_the_file_and_reports_new_directories(tmp_path):
    created = create_test_file(
        tmp_path, PurePosixPath("tests/unit/test_a.py"), "x = 1\n"
    )

    assert (tmp_path / "tests/unit/test_a.py").read_text() == "x = 1\n"
    assert created == [PurePosixPath("tests"), PurePosixPath("tests/unit")]
    assert undo_command(PurePosixPath("tests/unit/test_a.py"), created) == (
        "rm tests/unit/test_a.py && rmdir tests/unit && rmdir tests"
    )
    assert not list(tmp_path.rglob("*.devai-tmp"))


def test_existing_directory_is_not_reported(tmp_path):
    (tmp_path / "tests").mkdir()

    created = create_test_file(tmp_path, PurePosixPath("tests/test_a.py"), "x\n")

    assert created == []
    assert (
        undo_command(PurePosixPath("tests/test_a.py"), created) == "rm tests/test_a.py"
    )


def test_never_overwrites_a_file_that_appears_at_the_last_moment(tmp_path, monkeypatch):
    real_link = os.link

    def someone_creates_it_first(source, target):
        write(tmp_path, "tests/test_a.py", "the user's own tests\n")
        real_link(source, target)

    monkeypatch.setattr(create_module.os, "link", someone_creates_it_first)

    with pytest.raises(CreateError, match="appeared meanwhile"):
        create_test_file(tmp_path, PurePosixPath("tests/test_a.py"), "AI tests\n")

    assert (tmp_path / "tests/test_a.py").read_text() == "the user's own tests\n"
    assert not list(tmp_path.rglob("*.devai-tmp"))


def test_failure_removes_the_directories_it_created(tmp_path, monkeypatch):
    def broken_link(source, target):
        raise OSError("read-only file system")

    monkeypatch.setattr(create_module.os, "link", broken_link)

    with pytest.raises(CreateError, match="couldn't create"):
        create_test_file(tmp_path, PurePosixPath("new/dir/test_a.py"), "x\n")

    assert not (tmp_path / "new").exists()
