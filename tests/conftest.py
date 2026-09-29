import os
import shutil
import subprocess
from pathlib import Path

import pytest


def make_files(root: Path, *relative_paths: str) -> None:
    """Create each file (and its parent directories) under `root`."""
    for relative in relative_paths:
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("x")


@pytest.fixture
def git_repo(tmp_path, tmp_path_factory, monkeypatch):
    """A throwaway git repository in tmp_path, isolated from user git config."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    # Keep the developer's git config out. Git reads the global excludes file
    # from $XDG_CONFIG_HOME/git/ignore (or ~/.config/git/ignore) even without
    # a config file, so HOME and XDG_CONFIG_HOME must point somewhere empty.
    empty_home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(empty_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(empty_home / ".config"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def git_add(repo: Path, *paths: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", *paths], check=True)
