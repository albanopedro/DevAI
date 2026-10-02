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
    collect_ignore += [
        "test_ollama_client.py",
        "test_opencode_client.py",
        "test_review_ai.py",
        "test_chat_ai.py",
        "test_chat_session.py",
        "test_fix_edits.py",
        "test_fix_ai.py",
        "test_fix_apply.py",
        "test_testgen.py",
    ]


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


def git_commit(repo: Path, message: str = "test commit") -> None:
    """Commit everything in a THROWAWAY test repository (never the user's)."""
    identity = ["-c", "user.name=DevAI Test", "-c", "user.email=test@example.invalid"]
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), *identity, "commit", "-q", "-m", message], check=True
    )


def git_run(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def write(root: Path, relative: str, text: str) -> None:
    """Create `root/relative` with `text`, creating parent directories."""
    make_files(root, relative)
    (root / relative).write_text(text)


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


def fake_review_report(issues=None, **overrides):
    """A valid AIReviewReport, as a model would return it (requires [ai])."""
    from devai.review.schema import AIReviewReport, ReviewIssue

    if issues is None:
        issues = [
            ReviewIssue(
                file="app.py",
                line=2,
                severity="medium",
                category="bug",
                title="Changed return value",
                explanation="main() now returns 2; callers expecting 1 may break.",
                suggestion="Check the callers or keep returning 1.",
            )
        ]
    fields = dict(
        summary="Changes the value returned by main().",
        issues=issues,
        suggested_tests=["Test that main() returns the new value."],
        limitations=["Only the changed lines were visible."],
    )
    return AIReviewReport(**(fields | overrides))


def fake_chat_answer(sources=None, suggested_files=None, **overrides):
    """A valid ChatAnswer, as a model would return it (requires [ai])."""
    from devai.chat.schema import ChatAnswer

    fields = dict(
        answer="get_user raises Error(500) unconditionally, so every call fails.",
        sources=["api/users.py:2"] if sources is None else sources,
        suggested_files=[] if suggested_files is None else suggested_files,
    )
    return ChatAnswer(**(fields | overrides))


def fake_fix_proposal(edits=None, **overrides):
    """A valid FixProposal, as a model would return it (requires [ai])."""
    from devai.fix.schema import FixEdit, FixProposal

    if edits is None:
        edits = [
            FixEdit(
                file="stats.py",
                old_text="def percent(part, whole):\n    return part / whole * 100",
                new_text=(
                    "def percent(part, whole):\n"
                    "    if whole == 0:\n"
                    '        raise ValueError("whole must not be zero")\n'
                    "    return part / whole * 100"
                ),
                reason="Avoid ZeroDivisionError",
            )
        ]
    fields = dict(
        summary="Reject a zero total with a clear error.",
        edits=edits,
        risks=["Callers that expected ZeroDivisionError now get ValueError."],
        tests=["Test that percent(1, 0) raises ValueError."],
    )
    return FixProposal(**(fields | overrides))


def fake_generated_tests(
    path="tests/test_stats_edge_cases.py", content=None, **overrides
):
    """A valid GeneratedTests, as a model would return it (requires [ai])."""
    from devai.testgen.schema import GeneratedTests

    if content is None:
        content = (
            "import pytest\n"
            "from stats import percent\n"
            "\n"
            "\n"
            "def test_percent_of_zero_whole_raises():\n"
            "    with pytest.raises(ZeroDivisionError):\n"
            "        percent(1, 0)\n"
        )
    fields = dict(
        path=path,
        content=content,
        covers=["percent"],
        notes=["Assumes tests import modules from the project root."],
    )
    return GeneratedTests(**(fields | overrides))
