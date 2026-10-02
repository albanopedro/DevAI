import json
from pathlib import Path, PurePosixPath

import pytest
from conftest import FAKE_SECRETS, fake_generated_tests, git_commit, write

from devai.ai.settings import AISettings
from devai.chat.retrieval import SelectedFile
from devai.models import CheckReport, FileSource, ProjectInfo, TestSummary
from devai.testgen.ai import (
    TESTGEN_SYSTEM_PROMPT,
    generation_question,
    generation_request,
)
from devai.testgen.context import TESTGEN_CONTEXT_VERSION, build_testgen_context
from devai.testgen.create import run_command
from devai.testgen.schema import GeneratedTests
from devai.testgen.validate import TestGenError, validate_generated

SOURCE = PurePosixPath("stats.py")
INFO = ProjectInfo(
    name="demo",
    path=Path("/home/someone/private/demo"),
    file_count=2,
    file_source=FileSource.GIT,
    has_git=True,
    has_readme=False,
    tests=TestSummary(1, ("pytest",)),
)


def selected(path, text):
    return SelectedFile(PurePosixPath(path), "r", text)


# --- context --------------------------------------------------------------------------


def test_context_fields_are_an_explicit_allow_list():
    # If this fails, what a test proposal receives changed: decide it's safe (D046).
    context = build_testgen_context(
        selected("stats.py", "def f(): pass\n"),
        [selected("tests/test_stats.py", "def test_f(): pass\n")],
        ["f"],
        INFO,
        CheckReport(),
    )

    assert set(context) == {
        "testgen_context_version",
        "source",
        "existing_tests",
        "frameworks",
        "untested_names",
        "project",
        "redacted_lines",
        "truncated",
    }
    assert context["testgen_context_version"] == TESTGEN_CONTEXT_VERSION == 1
    assert context["frameworks"] == ["pytest"]
    assert context["untested_names"] == ["f"]


def test_context_redacts_and_caps_existing_tests():
    secret, _ = FAKE_SECRETS["secret/aws-access-key"]
    tests = [selected(f"tests/test_stats_{n}.py", "x\n") for n in range(3)]

    context = build_testgen_context(
        selected("stats.py", f"KEY = '{secret}'\n"), tests, [], INFO, CheckReport()
    )

    assert secret not in json.dumps(context)
    assert context["redacted_lines"] == 1
    assert len(context["existing_tests"]) == 2
    assert context["truncated"]["existing_tests"] == {"shown": 2, "total": 3}
    assert "/home/someone" not in json.dumps(context)


# --- task -----------------------------------------------------------------------------


def test_request_and_question():
    context = build_testgen_context(
        selected("stats.py", "x = 1\n"), [], [], INFO, CheckReport()
    )

    request = generation_request(context)
    question = generation_question(context, AISettings())

    assert request.system_prompt == TESTGEN_SYSTEM_PROMPT
    assert request.output is GeneratedTests
    assert request.title == "DevAI tests"
    assert "<testgen_context>\n" in request.message
    assert question.startswith("Send 1 file (~")
    assert question.endswith("to write tests? Files: stats.py.")
    assert "DevAI never runs them" in TESTGEN_SYSTEM_PROMPT


# --- validation -----------------------------------------------------------------------


@pytest.fixture
def project(git_repo):
    write(
        git_repo,
        "stats.py",
        "def percent(part, whole):\n    return part / whole * 100\n",
    )
    write(git_repo, "tests/test_stats.py", "def test_ok():\n    assert True\n")
    write(git_repo, ".gitignore", "generated/\n")
    git_commit(git_repo, "fixture")
    return git_repo


def check(project, **proposal):
    return validate_generated(fake_generated_tests(**proposal), project, SOURCE)


def test_valid_proposal(project):
    assert check(project) == PurePosixPath("tests/test_stats_edge_cases.py")


@pytest.mark.parametrize(
    ("proposal", "message"),
    [
        ({"path": "tests/test_stats.py"}, "already exists"),
        ({"path": "../test_stats.py"}, "outside the project"),
        ({"path": "/tmp/test_stats.py"}, "isn't a project-relative path"),
        ({"path": "generated/test_stats.py"}, "ignored by the project's .gitignore"),
        ({"path": "tests/stats_helpers.py"}, "naming conventions"),
        ({"path": "tests/test_cart.py"}, "doesn't contain stats.py's name"),
        ({"path": "tests/stats.test.js"}, "same language"),
        ({"content": "  \n"}, "empty"),
        ({"content": "x = 1\n" * 301}, "too long"),
        ({"content": "x = '[redacted: possible secret (AKIA…)]'\n"}, "hidden as a"),
        ({"content": "def test_broken(:\n"}, "aren't valid Python"),
    ],
)
def test_rules(project, proposal, message):
    with pytest.raises(TestGenError, match=message):
        check(project, **proposal)


def test_a_secret_in_the_tests_is_rejected(project):
    secret, _ = FAKE_SECRETS["secret/stripe-key"]

    with pytest.raises(TestGenError, match="holds a possible secret"):
        check(project, content=f"KEY = '{secret}'\n")


def test_fake_passwords_in_tests_are_fine(project):
    assert check(project, content='password = "s3cr3tValue"\n')


def test_javascript_family_accepts_typescript_tests(tmp_path):
    write(tmp_path, "src/cart.js", "export const total = () => 0\n")

    path = validate_generated(
        fake_generated_tests(path="src/cart.test.ts", content="test('x', () => {})\n"),
        tmp_path,
        PurePosixPath("src/cart.js"),
    )

    assert path == PurePosixPath("src/cart.test.ts")


# --- run command (built by DevAI, never by the AI) ------------------------------------


@pytest.mark.parametrize(
    ("frameworks", "path", "command"),
    [
        (("pytest",), "tests/test_a.py", "pytest tests/test_a.py"),
        (("Jest",), "src/a.test.js", "npx jest src/a.test.js"),
        (("Vitest",), "src/a.test.ts", "npx vitest run src/a.test.ts"),
        (
            (),
            "tests/test a.py",
            "pytest 'tests/test a.py'  (install pytest first if needed)",
        ),
        ((), "src/a.test.js", "run src/a.test.js with your project's test runner"),
    ],
)
def test_run_command(frameworks, path, command):
    assert run_command(frameworks, PurePosixPath(path)) == command
