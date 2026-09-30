import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# AI client tests need the optional [ai] extra (Pydantic); without it, pytest
# doesn't collect them. The rest of DevAI must work without any extra.
collect_ignore = []
if importlib.util.find_spec("pydantic") is None:
    collect_ignore += ["test_ollama_client.py", "test_opencode_client.py"]


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


# Fake secrets are assembled at runtime, so no complete token ever appears in
# the source code: DevAI must not flag its own tests, and GitHub push
# protection must not block a push. The values are random-looking but fake.
FAKE_SECRETS = {
    "secret/aws-access-key": ("AKIA" + "Q7" * 8, "AKIA…"),
    "secret/github-token": ("ghp" + "_" + "a1B2" * 9, "ghp_…"),
    "secret/anthropic-key": ("sk-" + "ant-" + "api03-" + "a1B2" * 6, "sk-ant-…"),
    "secret/openai-key": ("sk-" + "proj-" + "a1B2" * 6, "sk-proj-…"),
    "secret/google-api-key": ("AI" + "za" + "a1B2c3D4e5" * 3 + "f6G7h", "AIza…"),
    "secret/slack-token": ("xo" + "xb-" + "1234567890-" + "a1B2" * 3, "xoxb-…"),
    "secret/stripe-key": ("sk" + "_live_" + "a1B2" * 6, "sk_live_…"),
}
FAKE_PRIVATE_KEY_HEADER = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"


def fake_ai_report(**overrides):
    """A valid AIReport, as the model would return it (requires the [ai] extra)."""
    from devai.ai.schema import AIRecommendation, AIReport, AIRisk

    fields = dict(
        summary="A small Python CLI that analyzes software projects.",
        risks=[
            AIRisk(
                title="Secrets committed",
                severity="high",
                explanation="An environment file is not ignored by git.",
                related_rule="env-not-ignored",
            )
        ],
        recommendations=[
            AIRecommendation(
                title="Ignore .env files",
                rationale="Prevents committing credentials.",
                effort="small",
            )
        ],
        limitations=["Source code was not reviewed."],
    )
    return AIReport(**(fields | overrides))
