import io
import json
import re
import subprocess
import sys

import pytest
from conftest import (
    FAKE_SECRETS,
    fake_ai_report,
    fake_chat_answer,
    fake_docs_proposal,
    fake_fix_proposal,
    fake_generated_tests,
    fake_readme_proposal,
    fake_review_report,
    git_commit,
    git_run,
    make_files,
    write,
)

from devai import __version__, cli
from devai.ai.result import AIError, AIResult, AIUsage
from devai.cli import EXIT_AI_ERROR, EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"devai {__version__}"


def test_help_lists_analyze_command(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    assert exit_info.value.code == 0
    assert "analyze" in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == EXIT_USAGE
    assert "usage: devai" in capsys.readouterr().out


def test_analyze_prints_project_info(tmp_path, capsys):
    project = tmp_path / "demo"
    make_files(
        project,
        "README.md",
        "pyproject.toml",
        "src/app.py",
        "src/index.js",
        "tests/test_app.py",
        "Dockerfile",
    )
    (project / "pyproject.toml").write_text(
        '[project]\ndependencies = ["Flask"]\n'
        '[project.optional-dependencies]\ndev = ["pytest"]\n'
    )

    assert main(["analyze", str(project)]) == EXIT_OK

    assert capsys.readouterr().out == (
        "DEVAI ANALYSIS\n"
        "────────────────────────────────────\n"
        "Project:        demo\n"
        f"Path:           {project.resolve()}\n"
        "Files:          6 (filesystem)\n"
        "Git repository: no\n"
        "README:         yes\n"
        "\n"
        "Languages:\n"
        "  Python      2 files   67%\n"
        "  JavaScript  1 file    33%\n"
        "\n"
        "Frameworks:\n"
        "  Flask\n"
        "\n"
        "Dependencies:\n"
        "  pyproject.toml  1 runtime, 1 dev\n"
        "\n"
        "Tests:\n"
        "  1 file (pytest)\n"
        "\n"
        "Configuration:\n"
        "  Dockerfile\n"
        "\n"
        "Structure:\n"
        "  src/    2 files\n"
        "  tests/  1 file\n"
        "  (root)  3 files\n"
        "\n"
        "Findings:\n"
        "  ⚠ LOW     No .gitignore found\n"
        "\n"
        "Passed:\n"
        "  ✓ README found\n"
        "  ✓ Tests found (1 file)\n"
        "  ✓ No exposed .env files\n"
        "  ✓ No known secret patterns found\n"
        "\n"
        "Secrets scan: 6 files scanned, 0 skipped\n"
    )


def test_analyze_empty_directory(tmp_path, capsys):
    assert main(["analyze", str(tmp_path)]) == EXIT_OK

    out = capsys.readouterr().out
    assert "Files:          0 (filesystem)" in out
    for section in [
        "Languages",
        "Frameworks",
        "Dependencies",
        "Tests",
        "Configuration",
    ]:
        assert f"{section}:\n  none detected" in out
    assert "Structure:\n  empty" in out


def test_analyze_prints_warnings(tmp_path, capsys):
    (tmp_path / ".git").mkdir()

    assert main(["analyze", str(tmp_path)]) == EXIT_OK
    assert "Warnings:\n  ! A .git directory exists" in capsys.readouterr().out


def test_analyze_defaults_to_current_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["analyze"]) == EXIT_OK
    assert f"Project:        {tmp_path.name}" in capsys.readouterr().out


def test_analyze_invalid_path(tmp_path, capsys):
    missing = tmp_path / "missing"

    assert main(["analyze", str(missing)]) == EXIT_USAGE

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not a directory" in captured.err


def test_python_dash_m_runs_end_to_end(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "devai", "analyze", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == EXIT_OK
    assert "DEVAI ANALYSIS" in result.stdout


def project_with_secret(root):
    secret, _ = FAKE_SECRETS["secret/aws-access-key"]
    make_files(root, "README.md", ".gitignore", "tests/test_app.py", "src/config.ts")
    (root / "src" / "config.ts").write_text(
        f"// config\nexport const key = '{secret}';\n"
    )
    return secret


def test_findings_show_severity_evidence_and_location(tmp_path, capsys):
    project_with_secret(tmp_path)

    main(["analyze", str(tmp_path)])

    assert (
        "Findings:\n"
        "  ⚠ HIGH    Possible AWS access key (AKIA…)\n"
        "            src/config.ts:2\n"
    ) in capsys.readouterr().out


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_full_secret_never_appears_in_output(tmp_path, capsys, output_format):
    secret = project_with_secret(tmp_path)

    main(["analyze", str(tmp_path), "--format", output_format])

    out = capsys.readouterr().out
    assert secret not in out
    assert secret[4:] not in out  # not even the part after the public prefix


@pytest.mark.parametrize(
    ("fail_on", "expected"),
    [
        (None, EXIT_OK),  # default: never fail
        ("none", EXIT_OK),
        ("high", EXIT_FINDINGS),
        ("medium", EXIT_FINDINGS),
        ("low", EXIT_FINDINGS),
    ],
)
def test_fail_on_with_high_finding(tmp_path, capsys, fail_on, expected):
    project_with_secret(tmp_path)
    args = ["analyze", str(tmp_path)] + (["--fail-on", fail_on] if fail_on else [])

    assert main(args) == expected


def test_fail_on_threshold_ignores_less_severe_findings(tmp_path, capsys):
    make_files(tmp_path, "README.md", "tests/test_app.py")  # only no-gitignore (LOW)

    assert main(["analyze", str(tmp_path), "--fail-on", "medium"]) == EXIT_OK
    assert main(["analyze", str(tmp_path), "--fail-on", "low"]) == EXIT_FINDINGS


def test_invalid_fail_on_value_is_a_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["analyze", str(tmp_path), "--fail-on", "critical"])

    assert exit_info.value.code == EXIT_USAGE
    assert "invalid choice" in capsys.readouterr().err


def test_json_output_is_valid_json(tmp_path, capsys):
    project_with_secret(tmp_path)

    assert main(["analyze", str(tmp_path), "--format", "json"]) == EXIT_OK

    document = json.loads(capsys.readouterr().out)
    assert document["checks"]["findings"][0]["rule_id"] == "secret/aws-access-key"


# --- AI (Phase 3a: dry run only) ------------------------------------------------------


def test_ai_dry_run_shows_context_and_size(tmp_path, capsys):
    make_files(tmp_path, "app.py")

    assert main(["analyze", str(tmp_path), "--ai", "--dry-run"]) == EXIT_OK

    out = capsys.readouterr().out
    assert out.startswith("AI CONTEXT PREVIEW (dry run: nothing was sent)\n")
    assert '"context_version": 1' in out
    assert "tokens, estimated)" in out


def test_ai_dry_run_json_is_the_context_only(tmp_path, capsys):
    make_files(tmp_path, "app.py")

    main(["analyze", str(tmp_path), "--ai", "--dry-run", "--format", "json"])

    assert json.loads(capsys.readouterr().out)["project"]["name"] == tmp_path.name


def test_ai_dry_run_makes_no_network_calls(tmp_path, capsys, monkeypatch):
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", no_network)
    make_files(tmp_path, "app.py")

    assert main(["analyze", str(tmp_path), "--ai", "--dry-run"]) == EXIT_OK


def test_dry_run_requires_ai(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["analyze", str(tmp_path), "--dry-run"])

    assert exit_info.value.code == EXIT_USAGE
    assert "--dry-run requires --ai" in capsys.readouterr().err


# --- AI (Phase 3b): the model is always a fake here, never the network ----------------


class FakeLLMClient:
    def __init__(self, result=None, error=None):
        self.requests = []
        self.result = result or AIResult(
            fake_ai_report(), "fake-model", AIUsage(10, 20)
        )
        self.error = error

    def complete(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result

    @property
    def contexts(self):
        """The contexts actually sent: the JSON between the request's tags."""
        return [extract_tagged_json(request.message) for request in self.requests]


def extract_tagged_json(message):
    match = re.search(r"<(\w+)>\n(.*)\n</\1>", message, re.DOTALL)
    return json.loads(match.group(2))


@pytest.fixture
def fake_ai(monkeypatch):
    """Replace the AI client (never a real model); simulate no terminal."""
    pytest.importorskip("pydantic")  # AIReport needs the optional [ai] extra
    client = FakeLLMClient()
    monkeypatch.setattr(cli, "create_ai_client", lambda settings: client)
    monkeypatch.setattr(cli, "is_interactive", lambda: False)
    for variable in ["DEVAI_AI_MODEL", "DEVAI_AI_PROVIDER"]:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    return client


def answer(monkeypatch, text):
    """Pretend to be a terminal where the user types `text`."""
    monkeypatch.setattr(cli, "is_interactive", lambda: True)
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def test_ai_with_yes_adds_the_ai_section(tmp_path, capsys, fake_ai):
    make_files(tmp_path, "app.py")

    assert main(["analyze", str(tmp_path), "--ai", "--yes"]) == EXIT_OK

    captured = capsys.readouterr()
    assert "Findings:" in captured.out  # the deterministic report comes first
    assert "AI ANALYSIS (fake-model)" in captured.out
    assert "  ⚠ HIGH    Secrets committed" in captured.out
    assert "  1. Ignore .env files [small effort]" in captured.out
    assert "Tokens: 10 in / 20 out" in captured.out
    assert "Analyzing with opencode/space-bunny-free…" in captured.err
    assert len(fake_ai.contexts) == 1


def test_ai_sends_the_same_context_as_the_dry_run(tmp_path, capsys, fake_ai):
    make_files(tmp_path, "app.py")
    main(["analyze", str(tmp_path), "--ai", "--dry-run", "--format", "json"])
    previewed = json.loads(capsys.readouterr().out)

    main(["analyze", str(tmp_path), "--ai", "--yes"])

    assert fake_ai.contexts == [previewed]


@pytest.mark.parametrize("typed", ["y\n", "yes\n", "Y\n"])
def test_consent_yes_sends(tmp_path, capsys, fake_ai, monkeypatch, typed):
    answer(monkeypatch, typed)

    assert main(["analyze", str(tmp_path), "--ai"]) == EXIT_OK

    assert len(fake_ai.contexts) == 1
    assert (
        "no source code) to OpenCode (opencode/space-bunny-free, free model)?"
        in capsys.readouterr().err
    )


@pytest.mark.parametrize("typed", ["n\n", "\n", "", "whatever\n"])
def test_anything_but_yes_sends_nothing(tmp_path, capsys, fake_ai, monkeypatch, typed):
    answer(monkeypatch, typed)

    assert main(["analyze", str(tmp_path), "--ai"]) == EXIT_OK

    captured = capsys.readouterr()
    assert fake_ai.contexts == []
    assert "Nothing was sent" in captured.err
    assert "Findings:" in captured.out  # the local report is still shown
    assert (
        "AI ANALYSIS (" not in captured.out
    )  # "DEVAI ANALYSIS" also matches "AI ANALYSIS"


def test_non_interactive_without_yes_refuses(tmp_path, capsys, fake_ai):
    assert main(["analyze", str(tmp_path), "--ai"]) == EXIT_USAGE

    captured = capsys.readouterr()
    assert fake_ai.contexts == []
    assert captured.out == ""
    assert "add --yes to confirm" in captured.err


def test_yes_requires_ai(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["analyze", str(tmp_path), "--yes"])

    assert exit_info.value.code == EXIT_USAGE


def test_ai_failure_still_prints_the_report(tmp_path, capsys, fake_ai):
    fake_ai.error = AIError("OpenCode is not installed.")

    assert main(["analyze", str(tmp_path), "--ai", "--yes"]) == EXIT_AI_ERROR

    captured = capsys.readouterr()
    assert "Findings:" in captured.out
    assert "AI analysis failed: OpenCode is not installed." in captured.err


def test_ai_json_output(tmp_path, capsys, fake_ai):
    make_files(tmp_path, "app.py")

    main(["analyze", str(tmp_path), "--ai", "--yes", "--format", "json"])

    document = json.loads(capsys.readouterr().out)  # stdout is pure JSON
    assert document["schema_version"] == 1
    assert document["ai"]["model"] == "fake-model"
    assert document["ai"]["usage"] == {"input_tokens": 10, "output_tokens": 20}
    assert document["ai"]["report"]["risks"][0]["severity"] == "high"


def test_fail_on_ignores_the_ai_opinion(tmp_path, capsys, fake_ai):
    # The fake AI reports a HIGH risk; the project itself has no HIGH finding.
    make_files(tmp_path, "README.md", ".gitignore", "tests/test_app.py")

    assert main(["analyze", str(tmp_path), "--ai", "--yes", "--fail-on", "high"]) == 0


@pytest.mark.parametrize("provider", ["opencode", "ollama"])
def test_missing_ai_extra_explains_how_to_install(
    tmp_path, capsys, monkeypatch, provider
):
    monkeypatch.setitem(sys.modules, "pydantic", None)  # makes `import pydantic` fail
    for module in [
        "devai.ai.opencode_client",
        "devai.ai.ollama_client",
        "devai.ai.schema",
    ]:
        monkeypatch.delitem(sys.modules, module, raising=False)

    args = ["analyze", str(tmp_path), "--ai", "--yes", "--provider", provider]
    assert main(args) == EXIT_USAGE
    assert "pip install 'devai[ai]'" in capsys.readouterr().err


def test_paid_model_is_refused_before_anything_runs(
    tmp_path, capsys, fake_ai, monkeypatch
):
    # The primordial rule: DevAI must never cost anything.
    monkeypatch.setenv("DEVAI_AI_MODEL", "opencode/claude-opus-5-5")

    assert main(["analyze", str(tmp_path), "--ai", "--yes"]) == EXIT_USAGE

    captured = capsys.readouterr()
    assert "only uses OpenCode's free models" in captured.err
    assert captured.out == ""
    assert fake_ai.contexts == []


def test_consent_warns_when_a_free_model_may_use_the_data(
    tmp_path, capsys, fake_ai, monkeypatch
):
    monkeypatch.setenv("DEVAI_AI_MODEL", "big-pickle")
    answer(monkeypatch, "n\n")

    main(["analyze", str(tmp_path), "--ai"])

    assert "Note: this free model may use your data to improve it." in (
        capsys.readouterr().err
    )


def test_ai_text_is_stripped_of_control_characters(tmp_path, capsys, fake_ai):
    hostile = "Looks fine\x1b[2J\x1b[31m and more\nnew line"
    fake_ai.result = AIResult(
        fake_ai_report(summary=hostile), "fake-model", AIUsage(1, 1)
    )

    main(["analyze", str(tmp_path), "--ai", "--yes"])

    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "Looks fine [2J [31m and more new line" in out  # each control char → space


# --- providers (Phase 3.5) ------------------------------------------------------------


def test_local_ollama_runs_without_asking(tmp_path, capsys, fake_ai):
    # Not a terminal and no --yes: fine, because nothing leaves the machine.
    assert main(["analyze", str(tmp_path), "--ai", "--provider", "ollama"]) == EXIT_OK

    captured = capsys.readouterr()
    assert len(fake_ai.contexts) == 1
    assert "[y/N]" not in captured.err
    assert "Analyzing locally with qwen3.5:9b (nothing leaves this machine)" in (
        captured.err
    )


def test_provider_can_come_from_the_environment(tmp_path, capsys, fake_ai, monkeypatch):
    monkeypatch.setenv("DEVAI_AI_PROVIDER", "ollama")

    assert main(["analyze", str(tmp_path), "--ai"]) == EXIT_OK
    assert "Analyzing locally" in capsys.readouterr().err


def test_remote_ollama_needs_consent(tmp_path, capsys, fake_ai, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "gpu-box")

    assert main(["analyze", str(tmp_path), "--ai", "--provider", "ollama"]) == 2

    assert fake_ai.contexts == []
    assert "Ollama at http://gpu-box:11434" in capsys.readouterr().err


def test_remote_ollama_asks_like_opencode(tmp_path, capsys, fake_ai, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "gpu-box")
    answer(monkeypatch, "n\n")

    main(["analyze", str(tmp_path), "--ai", "--provider", "ollama"])

    assert fake_ai.contexts == []
    assert "to Ollama at http://gpu-box:11434 (qwen3.5:9b)? " in capsys.readouterr().err


def test_provider_requires_ai(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["analyze", str(tmp_path), "--provider", "ollama"])

    assert exit_info.value.code == EXIT_USAGE


def test_create_ai_client_picks_the_provider():
    pytest.importorskip("pydantic")  # the [ai] extra
    from devai.ai.ollama_client import OllamaClient
    from devai.ai.opencode_client import OpenCodeClient
    from devai.ai.settings import AISettings

    assert isinstance(cli.create_ai_client(AISettings(provider="ollama")), OllamaClient)
    assert isinstance(cli.create_ai_client(AISettings()), OpenCodeClient)


# --- review (Phase 4a) ----------------------------------------------------------------


@pytest.fixture
def repo(git_repo):
    write(git_repo, "app.py", "def main():\n    return 1\n")
    write(git_repo, "tests/test_app.py", "def test_main():\n    assert True\n")
    git_commit(git_repo, "initial")
    return git_repo


def test_review_text_output(repo, capsys):
    write(repo, "app.py", "def main():\n    return 2\n")
    write(repo, "notes.md", "todo\n")

    assert main(["review", str(repo)]) == EXIT_OK

    assert capsys.readouterr().out == (
        "DEVAI REVIEW\n"
        "────────────────────────────────────\n"
        f"Project:  {repo.name}\n"
        "Changes:  working tree vs HEAD (staged, unstaged and untracked)\n"
        "Files:    2 changed (+2 -1)\n"
        "  M  app.py                +1 -1\n"
        "  A  notes.md (untracked)  +1\n"
        "\n"
        "Findings:\n"
        "  ⚠ MEDIUM  Code changed in 1 file(s) but no tests changed\n"
        "\n"
        "Passed:\n"
        "  ✓ No known secret patterns in added lines\n"
        "  ✓ No .env files in the changes\n"
        "  ✓ No debug statements added\n"
        "  ✓ Change size is reviewable (3 lines)\n"
        "\n"
        "Content checked: 2 files, 0 not read (env, lock, binary, large)\n"
    )


def test_review_with_no_changes(repo, capsys):
    assert main(["review", str(repo)]) == EXIT_OK

    assert capsys.readouterr().out.endswith("\nNo changes to review.\n")


def test_review_staged_catches_a_secret_before_commit(repo, capsys):
    secret, _ = FAKE_SECRETS["secret/aws-access-key"]
    write(repo, "config.py", f"KEY = '{secret}'\n")
    git_run(repo, "add", "config.py")

    code = main(["review", str(repo), "--staged", "--fail-on", "high"])

    out = capsys.readouterr().out
    assert code == EXIT_FINDINGS
    assert "⚠ HIGH    Possible AWS access key (AKIA…)\n            config.py:1" in out
    assert secret not in out


def test_review_base(repo, capsys):
    git_run(repo, "branch", "base")
    write(repo, "feature.py", "x = 1\n")
    git_commit(repo, "feature")

    main(["review", str(repo), "--base", "base"])

    out = capsys.readouterr().out
    assert "Changes:  committed changes since base (" in out
    assert "  A  feature.py  +1" in out


def test_review_json_never_contains_code(repo, capsys):
    secret, _ = FAKE_SECRETS["secret/github-token"]
    write(repo, "app.py", f"TOKEN = '{secret}'\nUNIQUE_CODE_MARKER = 1\n")

    main(["review", str(repo), "--format", "json"])

    out = capsys.readouterr().out
    document = json.loads(out)
    assert document["schema_version"] == 1
    assert document["review"]["files"][0]["path"] == "app.py"
    assert "UNIQUE_CODE_MARKER" not in out
    assert secret not in out


def test_review_outside_git_is_a_usage_error(tmp_path, capsys):
    assert main(["review", str(tmp_path)]) == EXIT_USAGE
    assert "needs a git repository" in capsys.readouterr().err


def test_review_unknown_base_is_a_usage_error(repo, capsys):
    assert main(["review", str(repo), "--base", "nope"]) == EXIT_USAGE
    assert "Can't compare with 'nope'" in capsys.readouterr().err


def test_review_staged_and_base_are_exclusive(repo, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["review", str(repo), "--staged", "--base", "main"])

    assert exit_info.value.code == EXIT_USAGE


# --- review --ai (Phase 4b: dry run only) ---------------------------------------------


def test_review_ai_dry_run_lists_what_would_be_sent(repo, capsys):
    write(repo, "app.py", "def main():\n    return 2\n")
    write(repo, ".env", "SECRET=1\n")

    assert main(["review", str(repo), "--ai", "--dry-run"]) == EXIT_OK

    out = capsys.readouterr().out
    assert out.startswith("AI REVIEW CONTEXT PREVIEW (dry run: nothing was sent)\n")
    assert "Code from these files would be sent (changed hunks only):\n" in out
    assert "  app.py  4 lines\n" in out  # header, context, removed, added
    assert "Not sent:\n  .env  not read (privacy or size rules)\n" in out
    assert "lines redacted" in out


def test_review_ai_dry_run_json_is_the_context_only(repo, capsys):
    write(repo, "app.py", "changed\n")

    main(["review", str(repo), "--ai", "--dry-run", "--format", "json"])

    assert json.loads(capsys.readouterr().out)["review_context_version"] == 1


def test_review_ai_dry_run_makes_no_network_calls(repo, capsys, monkeypatch):
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    write(repo, "app.py", "changed\n")

    assert main(["review", str(repo), "--ai", "--dry-run"]) == EXIT_OK


def test_review_dry_run_requires_ai(repo, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["review", str(repo), "--dry-run"])

    assert exit_info.value.code == EXIT_USAGE


# --- review --ai (Phase 4c): the model is always a fake -------------------------------


@pytest.fixture
def fake_review_ai(fake_ai):
    fake_ai.result = AIResult(fake_review_report(), "fake-model", AIUsage(30, 40))
    return fake_ai


def change_app(repo):
    write(repo, "app.py", "def main():\n    return 2\n")


def test_review_ai_adds_the_ai_review_section(repo, capsys, fake_review_ai):
    change_app(repo)

    assert main(["review", str(repo), "--ai", "--yes"]) == EXIT_OK

    captured = capsys.readouterr()
    out = captured.out
    assert out.index("DEVAI REVIEW") < out.index("AI REVIEW (fake-model)")
    assert "  ⚠ MEDIUM  [bug] Changed return value\n            app.py:2\n" in out
    assert "Suggestion: Check the callers or keep returning 1." in out
    assert "Tokens: 30 in / 40 out" in out
    assert "Reviewing with opencode/space-bunny-free…" in captured.err
    assert fake_review_ai.requests[0].title == "DevAI review"


def test_review_ai_sends_the_same_context_as_the_dry_run(repo, capsys, fake_review_ai):
    change_app(repo)
    main(["review", str(repo), "--ai", "--dry-run", "--format", "json"])
    previewed = json.loads(capsys.readouterr().out)

    main(["review", str(repo), "--ai", "--yes"])

    assert fake_review_ai.contexts == [previewed]


def test_review_ai_consent_lists_the_files(repo, capsys, fake_review_ai, monkeypatch):
    change_app(repo)
    answer(monkeypatch, "n\n")

    assert main(["review", str(repo), "--ai"]) == EXIT_OK

    err = capsys.readouterr().err
    assert "Send the changed code of 1 file (~" in err
    assert "Files: app.py. Preview it with --dry-run. [y/N]" in err
    assert "AI review skipped. Nothing was sent." in err
    assert fake_review_ai.requests == []


def test_review_ai_without_terminal_needs_yes(repo, capsys, fake_review_ai):
    change_app(repo)

    assert main(["review", str(repo), "--ai"]) == EXIT_USAGE
    assert fake_review_ai.requests == []


def test_review_ai_with_local_ollama_does_not_ask(repo, capsys, fake_review_ai):
    change_app(repo)

    assert main(["review", str(repo), "--ai", "--provider", "ollama"]) == EXIT_OK
    assert "Reviewing locally with qwen3.5:9b" in capsys.readouterr().err


def test_review_ai_skipped_when_no_code_can_be_sent(repo, capsys, fake_review_ai):
    write(repo, ".env", "SECRET=1\n")  # the only change: never sent

    assert main(["review", str(repo), "--ai", "--yes"]) == EXIT_OK

    assert "no code can be sent" in capsys.readouterr().err
    assert fake_review_ai.requests == []


def test_review_ai_discards_issues_about_unseen_files(repo, capsys, fake_review_ai):
    from devai.review.schema import ReviewIssue

    unseen = ReviewIssue(
        file="secret_config.py",
        line=1,
        severity="high",
        category="security",
        title="Invented",
        explanation="Not in the diff.",
        suggestion="None.",
    )
    fake_review_ai.result = AIResult(
        fake_review_report(issues=[unseen]), "fake-model", AIUsage(1, 1)
    )
    change_app(repo)

    main(["review", str(repo), "--ai", "--yes"])

    out = capsys.readouterr().out
    assert "Invented" not in out
    assert "Discarded 1 issue about files whose code the AI didn't see." in out


def test_review_ai_json(repo, capsys, fake_review_ai):
    change_app(repo)

    main(["review", str(repo), "--ai", "--yes", "--format", "json"])

    document = json.loads(capsys.readouterr().out)
    assert document["ai"]["model"] == "fake-model"
    assert document["ai"]["discarded_issues"] == 0
    assert document["ai"]["report"]["issues"][0]["file"] == "app.py"


def test_review_ai_failure_still_prints_the_review(repo, capsys, fake_review_ai):
    fake_review_ai.error = AIError("OpenCode is not installed.")
    change_app(repo)

    assert main(["review", str(repo), "--ai", "--yes"]) == EXIT_AI_ERROR

    captured = capsys.readouterr()
    assert "DEVAI REVIEW" in captured.out
    assert "AI review failed: OpenCode is not installed." in captured.err


def test_review_fail_on_ignores_the_ai_opinion(repo, capsys, fake_review_ai):
    write(repo, "app.py", "def main():\n    return 2\n")
    write(repo, "tests/test_app.py", "def test_main():\n    assert main() == 2\n")

    args = ["review", str(repo), "--ai", "--yes", "--fail-on", "low"]
    assert main(args) == EXIT_OK  # the fake AI reports a MEDIUM issue


def test_review_paid_model_is_refused(repo, capsys, fake_review_ai, monkeypatch):
    monkeypatch.setenv("DEVAI_AI_MODEL", "opencode/claude-opus-5-5")
    change_app(repo)

    assert main(["review", str(repo), "--ai", "--yes"]) == EXIT_USAGE
    assert "only uses OpenCode's free models" in capsys.readouterr().err
    assert fake_review_ai.requests == []


def test_review_yes_requires_ai(repo, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["review", str(repo), "--yes"])

    assert exit_info.value.code == EXIT_USAGE


# --- chat (Phase 5a: dry run only) ----------------------------------------------------


@pytest.fixture
def chat_project(tmp_path):
    write(tmp_path, "api/users.py", "def get_user():\n    raise Error(500)\n")
    write(tmp_path, "README.md", "users api\n")
    return tmp_path


def test_chat_dry_run_shows_the_files_and_why(chat_project, capsys):
    args = ["chat", str(chat_project), "--ask", "why do users get 500?", "--dry-run"]

    assert main(args) == EXIT_OK

    out = capsys.readouterr().out
    assert out.startswith("AI CHAT CONTEXT PREVIEW (dry run: nothing was sent)\n")
    assert "Search terms: users, get, 500\n" in out  # "get" matters in code
    assert "  api/users.py  matches: users, get, 500  (2 lines)\n" in out
    assert "  README.md     matches: users  (1 line)\n" in out


def test_chat_dry_run_json(chat_project, capsys):
    main(["chat", str(chat_project), "--ask", "users", "--dry-run", "--format", "json"])

    document = json.loads(capsys.readouterr().out)
    assert document["chat_context_version"] == 2
    assert document["files"][0]["path"] == "api/users.py"


def test_chat_with_no_matches_sends_only_the_summary(chat_project, capsys):
    main(["chat", str(chat_project), "--ask", "why?", "--dry-run"])

    assert "only the project summary would be sent" in capsys.readouterr().out


def test_chat_file_outside_the_project_is_refused(chat_project, capsys):
    args = ["chat", str(chat_project), "--ask", "q", "--dry-run", "--file", "../x.py"]

    assert main(args) == EXIT_USAGE
    assert "outside the project" in capsys.readouterr().err


def test_chat_without_a_question_needs_a_terminal(chat_project, capsys):
    assert main(["chat", str(chat_project), "--dry-run"]) == EXIT_USAGE
    assert "needs a question" in capsys.readouterr().err


def test_chat_dry_run_makes_no_network_calls(chat_project, capsys, monkeypatch):
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", no_network)

    assert main(["chat", str(chat_project), "--ask", "users", "--dry-run"]) == EXIT_OK


# --- chat --ask with AI (Phase 5b, step 1): the model is always a fake ----------------


@pytest.fixture
def fake_chat_ai(fake_ai):
    fake_ai.result = AIResult(fake_chat_answer(), "fake-model", AIUsage(50, 60))
    return fake_ai


def test_chat_ask_answers_with_sources(chat_project, capsys, fake_chat_ai):
    args = ["chat", str(chat_project), "--ask", "why do users get 500?", "--yes"]

    assert main(args) == EXIT_OK

    captured = capsys.readouterr()
    out = captured.out
    assert out.index("DEVAI CHAT") < out.index("ANSWER (fake-model)")
    assert "  1. api/users.py  matches: users, get, 500  (2 lines)\n" in out
    assert "get_user raises Error(500)" in out
    assert "Sources:\n  api/users.py:2\n" in out
    assert "Asking opencode/space-bunny-free…" in captured.err
    assert fake_chat_ai.requests[0].title == "DevAI chat"


def test_chat_ask_sends_the_same_context_as_the_dry_run(
    chat_project, capsys, fake_chat_ai
):
    base = ["chat", str(chat_project), "--ask", "users 500"]
    main([*base, "--dry-run", "--format", "json"])
    previewed = json.loads(capsys.readouterr().out)

    main([*base, "--yes"])

    assert fake_chat_ai.contexts == [previewed]


def test_chat_ask_consent_lists_the_files(
    chat_project, capsys, fake_chat_ai, monkeypatch
):
    answer(monkeypatch, "\n")  # just Enter: no

    assert main(["chat", str(chat_project), "--ask", "users 500"]) == EXIT_OK

    err = capsys.readouterr().err
    assert "Send the question + 2 files (~" in err
    assert "Files: api/users.py, README.md." in err
    assert "AI chat skipped. Nothing was sent." in err
    assert fake_chat_ai.requests == []


def test_chat_ask_without_terminal_needs_yes(chat_project, capsys, fake_chat_ai):
    assert main(["chat", str(chat_project), "--ask", "users"]) == EXIT_USAGE
    assert fake_chat_ai.requests == []


def test_chat_ask_drops_invented_sources_and_bad_suggestions(
    chat_project, capsys, fake_chat_ai
):
    write(chat_project, "api/db.py", "def connect():\n    pass\n")
    write(chat_project, ".env", "DB=secret\n")
    fake_chat_ai.result = AIResult(
        fake_chat_answer(
            sources=["api/users.py:2", "api/invented.py:9", "README.md:999"],
            suggested_files=[
                {"path": "api/db.py", "reason": "the database layer"},
                {"path": ".env", "reason": "configuration"},
                {"path": "../outside.py", "reason": "nope"},
            ],
        ),
        "fake-model",
        AIUsage(1, 1),
    )

    main(["chat", str(chat_project), "--ask", "users 500", "--yes"])

    out = capsys.readouterr().out
    assert "Sources:\n  api/users.py:2\n  README.md\n" in out  # bad line → no line
    assert "  - api/db.py: the database layer" in out
    assert ".env" not in out.split("ANSWER")[1]
    assert "Dropped 1 source and 2 suggestions" in out


def test_chat_ask_json(chat_project, capsys, fake_chat_ai):
    main(["chat", str(chat_project), "--ask", "users 500", "--yes", "--format", "json"])

    document = json.loads(capsys.readouterr().out)
    assert document["chat"]["files"][0] == {
        "path": "api/users.py",
        "reason": "matches: users, 500",
    }
    assert document["ai"]["answer"]["sources"] == ["api/users.py:2"]
    assert document["ai"]["dropped_sources"] == 0


def test_chat_ask_failure_exits_3(chat_project, capsys, fake_chat_ai):
    fake_chat_ai.error = AIError("OpenCode is not installed.")

    assert main(["chat", str(chat_project), "--ask", "users", "--yes"]) == EXIT_AI_ERROR
    assert "AI chat failed: OpenCode is not installed." in capsys.readouterr().err


def test_chat_ask_paid_model_is_refused(
    chat_project, capsys, fake_chat_ai, monkeypatch
):
    monkeypatch.setenv("DEVAI_AI_MODEL", "opencode/gpt-5.5")

    assert main(["chat", str(chat_project), "--ask", "users", "--yes"]) == EXIT_USAGE
    assert fake_chat_ai.requests == []


# --- interactive chat from the CLI (Phase 5b, step 2) ---------------------------------


def test_interactive_chat_needs_a_terminal(chat_project, capsys, fake_chat_ai):
    assert main(["chat", str(chat_project)]) == EXIT_USAGE
    assert "needs a terminal" in capsys.readouterr().err


def test_interactive_chat_runs_in_a_terminal(
    chat_project, capsys, fake_chat_ai, monkeypatch
):
    typed = iter(["users 500", "y", "/quit"])
    monkeypatch.setattr(cli, "is_interactive", lambda: True)
    monkeypatch.setattr(cli, "read_line", lambda prompt: next(typed, None))

    assert main(["chat", str(chat_project), "--file", "README.md"]) == EXIT_OK

    out = capsys.readouterr().out
    assert "DEVAI CHAT · " in out
    assert "Added README.md: it goes with every next question." in out
    assert len(fake_chat_ai.requests) == 1


# --- fix (Phase 6a): proposals only, nothing is ever written --------------------------


STATS_PY = (
    "def average(values):\n"
    "    return sum(values) / len(values)\n"
    "\n"
    "\n"
    "def percent(part, whole):\n"
    "    return part / whole * 100\n"
)


@pytest.fixture
def fix_project(tmp_path):
    write(tmp_path, "stats.py", STATS_PY)
    write(tmp_path, "tests/test_stats.py", "def test_ok():\n    assert True\n")
    return tmp_path


@pytest.fixture
def fake_fix_ai(fake_ai):
    fake_ai.result = AIResult(fake_fix_proposal(), "fake-model", AIUsage(70, 80))
    return fake_ai


def snapshot(root):
    """Every file's bytes: proof that nothing was written."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def fix(project, *extra):
    return main(
        ["fix", str(project), "--file", "stats.py", "--ask", "handle zero", *extra]
    )


def test_fix_shows_a_validated_diff_and_writes_nothing(
    fix_project, capsys, fake_fix_ai
):
    before = snapshot(fix_project)

    assert fix(fix_project, "--yes") == EXIT_OK

    out = capsys.readouterr().out
    assert out.index("DEVAI FIX") < out.index("PROPOSED FIX (fake-model)")
    assert "--- a/stats.py\n+++ b/stats.py\n" in out
    assert '+        raise ValueError("whole must not be zero")\n' in out
    assert "Nothing was changed. To write this fix, run again with --apply." in out
    assert snapshot(fix_project) == before


def test_rejected_proposal_exits_3_and_writes_nothing(fix_project, capsys, fake_fix_ai):
    from devai.fix.schema import FixEdit

    fake_fix_ai.result = AIResult(
        fake_fix_proposal(
            edits=[FixEdit(file="stats.py", old_text="nope", new_text="x", reason="r")]
        ),
        "fake-model",
        AIUsage(1, 1),
    )
    before = snapshot(fix_project)

    assert fix(fix_project, "--yes") == EXIT_AI_ERROR

    captured = capsys.readouterr()
    assert "The proposed fix was rejected: edit 1: text not found" in captured.err
    assert "PROPOSED FIX" not in captured.out
    assert snapshot(fix_project) == before


def test_fix_sends_the_same_context_as_the_dry_run(fix_project, capsys, fake_fix_ai):
    fix(fix_project, "--dry-run", "--format", "json")
    previewed = json.loads(capsys.readouterr().out)

    fix(fix_project, "--yes")

    assert fake_fix_ai.contexts == [previewed]


def test_fix_consent_lists_the_files(fix_project, capsys, fake_fix_ai, monkeypatch):
    answer(monkeypatch, "n\n")

    assert fix(fix_project) == EXIT_OK

    err = capsys.readouterr().err
    assert "Send the request + 1 file (~" in err
    assert "Files: stats.py." in err
    assert fake_fix_ai.requests == []


def test_fix_json(fix_project, capsys, fake_fix_ai):
    fix(fix_project, "--yes", "--format", "json")

    document = json.loads(capsys.readouterr().out)
    assert document["fix"]["applied"] is False
    assert document["ai"]["rejected"] is None
    assert document["ai"]["diffs"]["stats.py"].startswith("--- a/stats.py")


def test_fix_requires_file_and_ask(fix_project, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["fix", str(fix_project), "--ask", "x"])
    assert exit_info.value.code == EXIT_USAGE

    with pytest.raises(SystemExit):
        main(["fix", str(fix_project), "--file", "stats.py"])


def test_fix_at_most_three_files(fix_project, capsys):
    args = ["fix", str(fix_project), "--ask", "x"]
    for name in ["a.py", "b.py", "c.py", "d.py"]:
        args += ["--file", name]

    assert main(args) == EXIT_USAGE
    assert "at most 3 files" in capsys.readouterr().err


def test_fix_file_gets_the_same_checks(fix_project, capsys, fake_fix_ai):
    write(fix_project, ".env", "SECRET=1\n")
    args = ["fix", str(fix_project), "--file", ".env", "--ask", "x", "--yes"]

    assert main(args) == EXIT_USAGE
    assert "never sent" in capsys.readouterr().err
    assert fake_fix_ai.requests == []


def test_fix_paid_model_is_refused(fix_project, capsys, fake_fix_ai, monkeypatch):
    monkeypatch.setenv("DEVAI_AI_MODEL", "anthropic/claude-sonnet-5-5")

    assert fix(fix_project, "--yes") == EXIT_USAGE
    assert fake_fix_ai.requests == []


# --- fix --apply (Phase 6b): writes only after "y", and only when safe ----------------


@pytest.fixture
def fix_repo(git_repo):
    write(git_repo, "stats.py", STATS_PY)
    write(git_repo, "tests/test_stats.py", "def test_ok():\n    assert True\n")
    git_commit(git_repo, "fixture")
    return git_repo


def git_state(repo):
    """HEAD and the index: they must never change (DevAI never commits or stages)."""
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout
    staged = subprocess.run(
        ["git", "-C", str(repo), "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
    ).stdout
    return head, staged


def apply(repo, *extra):
    return fix(repo, "--apply", "--yes", *extra)  # --yes skips only the send question


def test_apply_writes_the_fix_after_yes(fix_repo, capsys, fake_fix_ai, monkeypatch):
    before_git = git_state(fix_repo)
    answer(monkeypatch, "y\n")

    assert apply(fix_repo) == EXIT_OK

    captured = capsys.readouterr()
    assert "Apply this fix to 1 file (stats.py)? [y/N]" in captured.err
    assert "Applied to stats.py.\nUndo with: git restore stats.py" in captured.out
    assert "Nothing was committed." in captured.out
    text = (fix_repo / "stats.py").read_text()
    assert 'raise ValueError("whole must not be zero")' in text
    assert git_state(fix_repo) == before_git  # no commit, nothing staged


@pytest.mark.parametrize("reply", ["n\n", "\n", ""])
def test_anything_but_yes_writes_nothing(
    fix_repo, capsys, fake_fix_ai, monkeypatch, reply
):
    before = snapshot(fix_repo)
    answer(monkeypatch, reply)

    assert apply(fix_repo) == EXIT_OK

    assert "Not applied. Nothing was changed." in capsys.readouterr().out
    assert snapshot(fix_repo) == before


def test_apply_needs_a_terminal_even_with_yes(fix_repo, capsys, fake_fix_ai):
    before = snapshot(fix_repo)

    assert apply(fix_repo) == EXIT_USAGE  # fake_ai simulates no terminal

    assert "--apply needs a terminal" in capsys.readouterr().err
    assert fake_fix_ai.requests == []
    assert snapshot(fix_repo) == before


@pytest.mark.parametrize("option", [["--dry-run"], ["--format", "json"]])
def test_apply_cannot_be_combined(fix_repo, capsys, fake_fix_ai, monkeypatch, option):
    answer(monkeypatch, "y\n")

    assert apply(fix_repo, *option) == EXIT_USAGE
    assert "can't be combined" in capsys.readouterr().err


def test_uncommitted_changes_refuse_before_asking_the_ai(
    fix_repo, capsys, fake_fix_ai, monkeypatch
):
    write(fix_repo, "stats.py", STATS_PY + "# local edit\n")
    before = snapshot(fix_repo)
    answer(monkeypatch, "y\n")

    assert apply(fix_repo) == EXIT_USAGE

    assert "has uncommitted changes" in capsys.readouterr().err
    assert fake_fix_ai.requests == []  # no AI call wasted
    assert snapshot(fix_repo) == before


def test_untracked_file_is_refused(fix_repo, capsys, fake_fix_ai, monkeypatch):
    write(fix_repo, "new.py", "x = 1\n")
    answer(monkeypatch, "y\n")
    args = ["fix", str(fix_repo), "--file", "new.py", "--ask", "x", "--apply", "--yes"]

    assert main(args) == EXIT_USAGE
    assert "isn't tracked by git" in capsys.readouterr().err


def test_outside_git_is_refused(fix_project, capsys, fake_fix_ai, monkeypatch):
    answer(monkeypatch, "y\n")

    assert apply(fix_project) == EXIT_USAGE
    assert "--apply needs a git repository" in capsys.readouterr().err


def test_file_edited_during_the_proposal_is_not_overwritten(
    fix_repo, capsys, fake_fix_ai, monkeypatch
):
    original_complete = fake_fix_ai.complete

    def complete_while_user_edits(request):
        # The user saves the file in an editor while the AI is working.
        (fix_repo / "stats.py").write_text(STATS_PY + "# edited meanwhile\n")
        return original_complete(request)

    monkeypatch.setattr(fake_fix_ai, "complete", complete_while_user_edits)
    answer(monkeypatch, "y\n")

    assert apply(fix_repo) == EXIT_USAGE

    assert "changed after the fix was proposed" in capsys.readouterr().err
    assert (fix_repo / "stats.py").read_text().endswith("# edited meanwhile\n")


def test_no_edits_means_nothing_to_apply(fix_repo, capsys, fake_fix_ai, monkeypatch):
    fake_fix_ai.result = AIResult(
        fake_fix_proposal(edits=[]), "fake-model", AIUsage(1, 1)
    )
    answer(monkeypatch, "y\n")

    assert apply(fix_repo) == EXIT_OK
    assert "Apply this fix" not in capsys.readouterr().err


# --- test map (Phase 7a) --------------------------------------------------------------


@pytest.fixture
def map_project(tmp_path):
    write(tmp_path, "src/app.py", "def run():\n    pass\n\n\ndef stop():\n    pass\n")
    write(tmp_path, "src/cart.py", "class Cart:\n    pass\n")
    write(
        tmp_path,
        "tests/test_app.py",
        "from app import run\n\n\ndef test_run():\n    run()\n",
    )
    return tmp_path


def test_test_map_text(map_project, capsys):
    assert main(["test", str(map_project)]) == EXIT_OK

    assert capsys.readouterr().out == (
        "DEVAI TEST\n"
        "────────────────────────────────────\n"
        f"Project:  {map_project.name}\n"
        "Tests:    1 file\n"
        "Source:   2 files checked (Python)\n"
        "\n"
        "Without a matching test file (1):\n"
        "  src/cart.py\n"
        "\n"
        "Python names no test mentions (2 in 2 files):\n"
        "  src/app.py: stop\n"
        "  src/cart.py: Cart\n"
        "\n"
        "An estimate from file and symbol names, not a coverage measurement:\n"
        "code tested indirectly (through other functions) can look untested.\n"
    )


def test_test_map_json(map_project, capsys):
    main(["test", str(map_project), "--format", "json"])

    document = json.loads(capsys.readouterr().out)["test_map"]
    assert document["without_tests"] == ["src/cart.py"]
    assert document["untested_symbols"] == {
        "src/app.py": ["stop"],
        "src/cart.py": ["Cart"],
    }
    assert document["estimate"] is True


def test_test_map_with_no_sources(tmp_path, capsys):
    write(tmp_path, "README.md", "docs only\n")

    assert main(["test", str(tmp_path)]) == EXIT_OK
    assert "No Python, JavaScript or TypeScript source files" in capsys.readouterr().out


def test_test_map_runs_nothing(map_project, capsys, monkeypatch):
    import subprocess as subprocess_module

    real_run = subprocess_module.run

    def only_git(command, *args, **kwargs):
        assert command[0] == "git", f"unexpected command: {command}"
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess_module, "run", only_git)

    assert main(["test", str(map_project)]) == EXIT_OK


# --- test --ai (Phase 7b): proposals, created only after "y", never run ---------------


@pytest.fixture
def testgen_repo(git_repo):
    write(git_repo, "stats.py", STATS_PY)
    write(git_repo, "tests/test_stats.py", "def test_ok():\n    assert True\n")
    git_commit(git_repo, "fixture")
    return git_repo


@pytest.fixture
def fake_tests_ai(fake_ai):
    fake_ai.result = AIResult(fake_generated_tests(), "fake-model", AIUsage(90, 99))
    return fake_ai


def generate(repo, *extra):
    return main(["test", str(repo), "--file", "stats.py", "--ai", "--yes", *extra])


def test_proposal_is_shown_and_nothing_is_created(testgen_repo, capsys, fake_tests_ai):
    before = snapshot(testgen_repo)

    assert generate(testgen_repo) == EXIT_OK

    out = capsys.readouterr().out
    assert "Existing tests: tests/test_stats.py" in out
    assert "New file: tests/test_stats_edge_cases.py" in out
    assert "def test_percent_of_zero_whole_raises():" in out
    assert "Run them yourself with: pytest tests/test_stats_edge_cases.py" in out
    assert "Nothing was created." in out
    assert snapshot(testgen_repo) == before


def test_tests_sends_the_same_context_as_the_dry_run(
    testgen_repo, capsys, fake_tests_ai
):
    main(
        [
            "test",
            str(testgen_repo),
            "--file",
            "stats.py",
            "--ai",
            "--dry-run",
            "--format",
            "json",
        ]
    )
    previewed = json.loads(capsys.readouterr().out)

    generate(testgen_repo)

    assert fake_tests_ai.contexts == [previewed]


def test_apply_creates_the_file_after_yes(
    testgen_repo, capsys, fake_tests_ai, monkeypatch
):
    before_git = git_state(testgen_repo)
    answer(monkeypatch, "y\n")

    assert generate(testgen_repo, "--apply") == EXIT_OK

    captured = capsys.readouterr()
    assert "Create tests/test_stats_edge_cases.py? [y/N]" in captured.err
    assert "Undo with: rm tests/test_stats_edge_cases.py" in captured.out
    assert "Nothing was committed." in captured.out
    created = testgen_repo / "tests/test_stats_edge_cases.py"
    assert created.read_text() == fake_generated_tests().content
    assert git_state(testgen_repo) == before_git


def test_apply_without_yes_creates_nothing(
    testgen_repo, capsys, fake_tests_ai, monkeypatch
):
    before = snapshot(testgen_repo)
    answer(monkeypatch, "n\n")

    assert generate(testgen_repo, "--apply") == EXIT_OK

    assert "Not created. Nothing was changed." in capsys.readouterr().out
    assert snapshot(testgen_repo) == before


def test_apply_needs_a_terminal(testgen_repo, capsys, fake_tests_ai):
    assert generate(testgen_repo, "--apply") == EXIT_USAGE
    assert fake_tests_ai.requests == []


def test_rejected_proposal_creates_nothing(testgen_repo, capsys, fake_tests_ai):
    fake_tests_ai.result = AIResult(
        fake_generated_tests(path="tests/test_stats.py"), "fake-model", AIUsage(1, 1)
    )
    before = snapshot(testgen_repo)

    assert generate(testgen_repo) == EXIT_AI_ERROR

    assert "already exists; DevAI never overwrites" in capsys.readouterr().err
    assert snapshot(testgen_repo) == before


def test_consent_lists_the_files(testgen_repo, capsys, fake_tests_ai, monkeypatch):
    answer(monkeypatch, "\n")

    main(["test", str(testgen_repo), "--file", "stats.py", "--ai"])

    err = capsys.readouterr().err
    assert "Files: stats.py, tests/test_stats.py." in err
    assert fake_tests_ai.requests == []


def test_generated_tests_are_never_run(
    testgen_repo, capsys, fake_tests_ai, monkeypatch
):
    import subprocess as subprocess_module

    real_run = subprocess_module.run

    def only_git(command, *args, **kwargs):
        assert command[0] == "git", f"unexpected command: {command}"
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess_module, "run", only_git)
    answer(monkeypatch, "y\n")

    assert generate(testgen_repo, "--apply") == EXIT_OK


def test_options_need_ai(testgen_repo, capsys):
    assert main(["test", str(testgen_repo), "--file", "stats.py"]) == EXIT_USAGE
    assert "--file requires --ai" in capsys.readouterr().err


def test_ai_needs_a_supported_source_file(testgen_repo, capsys, fake_tests_ai):
    write(testgen_repo, "README.md", "docs\n")

    args = ["test", str(testgen_repo), "--file", "README.md", "--ai", "--yes"]
    assert main(args) == EXIT_USAGE
    assert "Python, JavaScript or TypeScript" in capsys.readouterr().err


def test_tests_json(testgen_repo, capsys, fake_tests_ai):
    generate(testgen_repo, "--format", "json")

    document = json.loads(capsys.readouterr().out)
    assert document["tests"]["created"] is False
    assert document["ai"]["path"] == "tests/test_stats_edge_cases.py"
    assert document["ai"]["rejected"] is None


# --- docs map (Phase 8a) --------------------------------------------------------------


@pytest.fixture
def docs_project(tmp_path):
    readme = "# Tool\n\n## Usage\n\n`npm run dev` or `npm run deploy`\n"
    write(tmp_path, "README.md", readme)
    write(tmp_path, "LICENSE", "MIT\n")
    write(tmp_path, "package.json", '{"scripts": {"dev": "vite"}}')
    write(tmp_path, "src/app.py", "def run():\n    pass\n")
    write(tmp_path, "web/api.js", "/** Call it. */\nexport function api() {}\n")
    return tmp_path


def test_docs_map_text(docs_project, capsys):
    assert main(["docs", str(docs_project)]) == EXIT_OK

    assert capsys.readouterr().out == (
        "DEVAI DOCS\n"
        "────────────────────────────────────\n"
        f"Project:     {docs_project.name}\n"
        "Source:      2 files checked (JavaScript, Python)\n"
        "Documented:  1 of 3 public names (33%)\n"
        "\n"
        "Names without docs (2 in 1 file):\n"
        "  src/app.py: (module), run\n"
        "  (module): the file has no module docstring.\n"
        "\n"
        "README.md:\n"
        "  Sections found:    usage, license (LICENSE file)\n"
        "  Sections missing:  installation, tests\n"
        "  npm scripts it runs that no package.json has (1):\n"
        "    npm run deploy  (line 5)\n"
        "\n"
        "An estimate: Python is parsed, JavaScript and TypeScript exports are found\n"
        "by pattern, and only /** */ counts as JSDoc. Not every name needs docs: use\n"
        "it to choose where to look. README sections are found by heading words.\n"
    )


def test_docs_map_json(docs_project, capsys):
    main(["docs", str(docs_project), "--format", "json"])

    document = json.loads(capsys.readouterr().out)["docs_map"]
    assert document["public_names"] == 3
    assert document["documented"] == 1
    assert document["undocumented"] == {"src/app.py": ["(module)", "run"]}
    assert document["readme"]["path"] == "README.md"
    assert document["readme"]["missing_sections"] == ["installation", "tests"]
    assert document["readme"]["missing_scripts"] == [
        {"command": "npm run deploy", "script": "deploy", "line": 5}
    ]
    assert document["estimate"] is True


def test_docs_map_when_everything_is_documented(tmp_path, capsys):
    write(tmp_path, "app.py", '"""App."""\n\n\ndef run():\n    """Run."""\n')
    write(tmp_path, "README.md", "# App\n\n`npm test`\n")
    write(tmp_path, "package.json", '{"scripts": {"test": "vitest"}}')

    assert main(["docs", str(tmp_path)]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Documented:  2 of 2 public names (100%)" in output
    assert "Every public name checked has docs." in output
    assert "npm scripts:       1 mentioned, found in package.json" in output


def test_docs_map_without_sources_or_readme(tmp_path, capsys):
    write(tmp_path, "notes.txt", "nothing to document\n")

    assert main(["docs", str(tmp_path)]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Documented:  no public functions or classes found" in output
    assert "No Python, JavaScript or TypeScript source files to check." in output
    assert "README: none found at the project root." in output


def test_docs_map_with_an_unreadable_package_json(tmp_path, capsys):
    write(tmp_path, "README.md", "`npm run dev`\n")
    write(tmp_path, "package.json", "{ not json")

    assert main(["docs", str(tmp_path)]) == EXIT_OK
    assert "not checked (a package.json couldn't be read)" in capsys.readouterr().out


def test_docs_map_of_a_readme_that_is_not_markdown(tmp_path, capsys):
    write(tmp_path, "README.rst", "Tool\n====\n")

    assert main(["docs", str(tmp_path)]) == EXIT_OK
    assert (
        "README.rst: not checked (only Markdown READMEs are read)."
        in capsys.readouterr().out
    )


def test_docs_map_of_a_missing_directory(tmp_path, capsys):
    assert main(["docs", str(tmp_path / "nope")]) == EXIT_USAGE
    assert "not a directory" in capsys.readouterr().err


def test_docs_map_runs_nothing_and_sends_nothing(docs_project, capsys, monkeypatch):
    import socket
    import subprocess as subprocess_module

    real_run = subprocess_module.run

    def only_git(command, *args, **kwargs):
        assert command[0] == "git", f"unexpected command: {command}"
        return real_run(command, *args, **kwargs)

    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(subprocess_module, "run", only_git)
    monkeypatch.setattr(socket, "socket", no_network)

    assert main(["docs", str(docs_project)]) == EXIT_OK


# --- docs --ai (Phase 8b): placed by DevAI, proven docs-only, written after "y" -------

DOCUMENTED_STATS_PY = (
    '"""Small statistics helpers."""\n'
    "\n"
    "def average(values):\n"
    '    """Return the arithmetic mean of values."""\n'
    "    return sum(values) / len(values)\n"
    "\n"
    "\n"
    "def percent(part, whole):\n"
    '    """Return part as a percentage of whole."""\n'
    "    return part / whole * 100\n"
)


@pytest.fixture
def docs_repo(git_repo):
    write(git_repo, "stats.py", STATS_PY)
    git_commit(git_repo, "fixture")
    return git_repo


@pytest.fixture
def fake_docs_ai(fake_ai):
    fake_ai.result = AIResult(fake_docs_proposal(), "fake-model", AIUsage(40, 50))
    return fake_ai


def document(repo, *extra):
    return main(["docs", str(repo), "--file", "stats.py", "--ai", "--yes", *extra])


def test_docs_are_shown_as_a_diff_and_nothing_is_written(
    docs_repo, capsys, fake_docs_ai
):
    before = snapshot(docs_repo)

    assert document(docs_repo) == EXIT_OK

    out = capsys.readouterr().out
    assert "File:     stats.py (Python)" in out
    assert "Names:    (module), average, percent" in out
    assert '+    """Return the arithmetic mean of values."""' in out
    assert "Added:  (module), average, percent" in out
    assert "Only documentation changed: checked." in out
    assert "Notes from the AI:\n  - average raises ZeroDivisionError" in out
    assert "To write these docs, run again with --apply." in out
    assert snapshot(docs_repo) == before
    assert fake_docs_ai.contexts[0]["names"] == ["(module)", "average", "percent"]


def test_docs_send_the_same_context_as_the_dry_run(docs_repo, capsys, fake_docs_ai):
    main(["docs", str(docs_repo), "--file", "stats.py", "--ai", "--dry-run"])
    assert "AI DOCS CONTEXT PREVIEW (dry run" in capsys.readouterr().out
    args = ["--file", "stats.py", "--ai", "--dry-run", "--format", "json"]
    main(["docs", str(docs_repo), *args])
    previewed = json.loads(capsys.readouterr().out)

    document(docs_repo)

    assert fake_docs_ai.contexts == [previewed]


def test_docs_apply_writes_after_yes(docs_repo, capsys, fake_docs_ai, monkeypatch):
    before_git = git_state(docs_repo)
    answer(monkeypatch, "y\n")

    assert document(docs_repo, "--apply") == EXIT_OK

    captured = capsys.readouterr()
    assert "Apply these docs to 1 file (stats.py)? [y/N]" in captured.err
    assert "Applied to stats.py.\nUndo with: git restore stats.py" in captured.out
    assert (docs_repo / "stats.py").read_text() == DOCUMENTED_STATS_PY
    assert git_state(docs_repo) == before_git  # no commit, nothing staged


def test_docs_apply_writes_nothing_without_yes(
    docs_repo, capsys, fake_docs_ai, monkeypatch
):
    before = snapshot(docs_repo)
    answer(monkeypatch, "\n")

    assert document(docs_repo, "--apply") == EXIT_OK

    assert "Not applied. Nothing was changed." in capsys.readouterr().out
    assert snapshot(docs_repo) == before


def test_docs_apply_refuses_uncommitted_changes_before_any_ai_call(
    docs_repo, capsys, fake_docs_ai, monkeypatch
):
    write(docs_repo, "stats.py", STATS_PY + "\n# work in progress\n")
    answer(monkeypatch, "y\n")

    assert document(docs_repo, "--apply") == EXIT_USAGE

    assert "uncommitted changes" in capsys.readouterr().err
    assert fake_docs_ai.requests == []


def test_docs_apply_needs_a_terminal(docs_repo, capsys, fake_docs_ai):
    assert document(docs_repo, "--apply") == EXIT_USAGE
    assert "--apply needs a terminal" in capsys.readouterr().err


def test_docs_unsafe_text_is_rejected_and_nothing_is_written(
    docs_repo, capsys, fake_ai, monkeypatch
):
    injected = 'Mean."""\nimport os\nos.system("rm -rf ~")\n"""'
    fake_ai.result = AIResult(
        fake_docs_proposal([("average", injected)]), "fake-model", AIUsage(1, 1)
    )
    before = snapshot(docs_repo)
    answer(monkeypatch, "y\n")

    assert document(docs_repo, "--apply") == EXIT_AI_ERROR

    err = capsys.readouterr().err
    assert 'The proposed docs were rejected: the docs for average contain """' in err
    assert "Apply these docs" not in err
    assert snapshot(docs_repo) == before


def test_docs_for_unknown_names_are_dropped(docs_repo, capsys, fake_ai):
    docs = [("average", "Return the mean."), ("median", "Invented.")]
    fake_ai.result = AIResult(fake_docs_proposal(docs), "fake-model", AIUsage(1, 1))

    assert document(docs_repo) == EXIT_OK

    out = capsys.readouterr().out
    assert "Added:  average" in out
    assert "Not used (1):\n  - median: not one of the names DevAI asked about" in out


def test_docs_json(docs_repo, capsys, fake_docs_ai):
    document(docs_repo, "--format", "json")

    document_json = json.loads(capsys.readouterr().out)
    assert document_json["docs"]["file"] == "stats.py"
    assert document_json["docs"]["applied"] is False
    assert document_json["ai"]["added"] == ["(module)", "average", "percent"]
    assert document_json["ai"]["dropped"] == []
    assert document_json["ai"]["diff"].startswith("--- a/stats.py\n")


def test_docs_for_javascript(docs_repo, capsys, fake_ai):
    write(docs_repo, "search.js", "export function search(query) {\n  return [];\n}\n")
    git_commit(docs_repo, "js")
    proposal = fake_docs_proposal([("search", "Find notes.\n\n@param {string} query")])
    fake_ai.result = AIResult(proposal, "fake-model", AIUsage(1, 1))

    args = ["docs", str(docs_repo), "--file", "search.js", "--ai", "--yes"]
    assert main(args) == EXIT_OK

    out = capsys.readouterr().out
    assert "+/**\n+ * Find notes.\n+ *\n+ * @param {string} query\n+ */" in out
    assert "a single\n/** */ comment right above an export" in out


def test_docs_for_a_documented_file_need_no_ai_call(docs_repo, capsys, fake_docs_ai):
    write(docs_repo, "stats.py", DOCUMENTED_STATS_PY)

    assert document(docs_repo) == EXIT_OK

    assert "Every public name in stats.py has docs. Nothing was sent." in (
        capsys.readouterr().out
    )
    assert fake_docs_ai.requests == []


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--file", "stats.py"], "--file requires --ai"),
        (["--apply"], "--apply requires --ai"),
        (["--ai", "--file", "README.md"], "Python, JavaScript or TypeScript"),
        (["--ai", "--file", "tests/test_stats.py"], "not tests or config files"),
        (["--ai", "--file", "broken.py"], "broken.py isn't valid Python"),
        (["--ai", "--file", "stats.py", "--apply", "--dry-run"], "can't be combined"),
    ],
)
def test_docs_usage_errors(docs_repo, capsys, fake_docs_ai, args, message):
    write(docs_repo, "README.md", "# Stats\n")
    write(docs_repo, "tests/test_stats.py", "def test_ok():\n    pass\n")
    write(docs_repo, "broken.py", "def broken(:\n")

    assert main(["docs", str(docs_repo), *args]) == EXIT_USAGE

    assert message in capsys.readouterr().err
    assert fake_docs_ai.requests == []


# --- docs --readme --ai (Phase 8c): sections added, commands checked ------------------

STATS_README = "# Stats\n\nTiny stats helpers.\n\n## License\n\nMIT\n"
COMPLETE_README = (
    "# Stats\n"
    "\n"
    "Tiny stats helpers.\n"
    "\n"
    "## Installation\n"
    "\n"
    "```bash\n"
    "npm install\n"
    "```\n"
    "\n"
    "## Usage\n"
    "\n"
    "```bash\n"
    "npm run dev\n"
    "```\n"
    "\n"
    "## Running tests\n"
    "\n"
    "```bash\n"
    "npm test\n"
    "```\n"
    "\n"
    "## License\n"
    "\n"
    "MIT\n"
)


@pytest.fixture
def readme_repo(git_repo):
    write(git_repo, "README.md", STATS_README)
    write(git_repo, "package.json", '{"scripts": {"dev": "vite", "test": "vitest"}}')
    write(git_repo, "stats.js", "export function mean(values) {}\n")
    write(git_repo, "tests/stats.test.js", "test('mean', () => {});\n")
    git_commit(git_repo, "fixture")
    return git_repo


@pytest.fixture
def fake_readme_ai(fake_ai):
    fake_ai.result = AIResult(fake_readme_proposal(), "fake-model", AIUsage(60, 70))
    return fake_ai


def write_readme(repo, *extra):
    return main(["docs", str(repo), "--readme", "--ai", "--yes", *extra])


def test_readme_sections_are_shown_and_nothing_is_written(
    readme_repo, capsys, fake_readme_ai
):
    before = snapshot(readme_repo)

    assert write_readme(readme_repo) == EXIT_OK

    out = capsys.readouterr().out
    assert "README:   README.md\nTopics:   installation, usage, tests" in out
    assert "+## Installation" in out
    assert (
        "Added:  Installation (installation), Usage (usage), Running tests (tests)"
        in out
    )
    assert "Only additions: checked." in out
    assert "To write these sections, run again with --apply." in out
    assert snapshot(readme_repo) == before
    sent = fake_readme_ai.contexts[0]
    assert sent["topics"] == ["installation", "usage", "tests"]
    scripts = sent["scripts"]["package.json"]["scripts"]
    assert scripts == {"dev": "vite", "test": "vitest"}
    assert "export function mean" not in json.dumps(sent)  # no source code


def test_readme_sends_the_same_context_as_the_dry_run(
    readme_repo, capsys, fake_readme_ai
):
    args = ["docs", str(readme_repo), "--readme", "--ai", "--dry-run"]
    main([*args, "--format", "json"])
    previewed = json.loads(capsys.readouterr().out)

    write_readme(readme_repo)

    assert fake_readme_ai.contexts == [previewed]


def test_readme_apply_writes_after_yes(
    readme_repo, capsys, fake_readme_ai, monkeypatch
):
    before_git = git_state(readme_repo)
    answer(monkeypatch, "y\n")

    assert write_readme(readme_repo, "--apply") == EXIT_OK

    captured = capsys.readouterr()
    assert "Apply these sections to 1 file (README.md)? [y/N]" in captured.err
    assert "Undo with: git restore README.md" in captured.out
    assert (readme_repo / "README.md").read_text() == COMPLETE_README
    assert git_state(readme_repo) == before_git


def test_readme_apply_writes_nothing_without_yes(
    readme_repo, capsys, fake_readme_ai, monkeypatch
):
    before = snapshot(readme_repo)
    answer(monkeypatch, "n\n")

    assert write_readme(readme_repo, "--apply") == EXIT_OK

    assert "Not applied. Nothing was changed." in capsys.readouterr().out
    assert snapshot(readme_repo) == before


def test_readme_apply_refuses_uncommitted_changes_before_any_ai_call(
    readme_repo, capsys, fake_readme_ai, monkeypatch
):
    write(readme_repo, "README.md", STATS_README + "\nDraft.\n")
    answer(monkeypatch, "y\n")

    assert write_readme(readme_repo, "--apply") == EXIT_USAGE

    assert "uncommitted changes" in capsys.readouterr().err
    assert fake_readme_ai.requests == []


def test_a_new_readme_is_created_after_yes(git_repo, capsys, fake_ai, monkeypatch):
    write(git_repo, "package.json", '{"scripts": {"dev": "vite"}}')
    write(git_repo, "stats.js", "export function mean(values) {}\n")
    git_commit(git_repo, "no readme")
    sections = [("usage", "Usage", "```bash\nnpm run dev\n```")]
    proposal = fake_readme_proposal(sections, description="Tiny stats helpers.")
    fake_ai.result = AIResult(proposal, "fake-model", AIUsage(1, 1))
    before_git = git_state(git_repo)
    answer(monkeypatch, "y\n")

    assert write_readme(git_repo, "--apply") == EXIT_OK

    captured = capsys.readouterr()
    assert "README:   none yet: a new README.md" in captured.out
    assert "Create README.md? [y/N]" in captured.err
    assert "Created README.md.\nUndo with: rm README.md" in captured.out
    assert (git_repo / "README.md").read_text() == (
        f"# {git_repo.name}\n\nTiny stats helpers.\n\n"
        "## Usage\n\n```bash\nnpm run dev\n```\n"
    )
    assert git_state(git_repo) == before_git


def test_unsafe_readme_text_is_rejected(readme_repo, capsys, fake_ai, monkeypatch):
    sections = [("usage", "Usage", "<script>steal()</script>")]
    fake_ai.result = AIResult(fake_readme_proposal(sections), "fake", AIUsage(1, 1))
    before = snapshot(readme_repo)
    answer(monkeypatch, "y\n")

    assert write_readme(readme_repo, "--apply") == EXIT_AI_ERROR

    err = capsys.readouterr().err
    assert "The proposed README sections were rejected" in err
    assert "HTML that runs code" in err
    assert snapshot(readme_repo) == before


def test_a_section_with_a_missing_script_is_dropped(readme_repo, capsys, fake_ai):
    sections = [
        ("installation", "Installation", "```bash\nnpm install\n```"),
        ("usage", "Usage", "```bash\nnpm run deploy\n```"),
    ]
    fake_ai.result = AIResult(fake_readme_proposal(sections), "fake", AIUsage(1, 1))

    assert write_readme(readme_repo) == EXIT_OK

    out = capsys.readouterr().out
    assert "Added:  Installation (installation)" in out
    assert (
        "Not used (1):\n"
        "  - usage (Usage): `npm run deploy` runs a script no package.json has"
    ) in out


def test_readme_json(readme_repo, capsys, fake_readme_ai):
    write_readme(readme_repo, "--format", "json")

    document_json = json.loads(capsys.readouterr().out)
    assert document_json["readme"]["path"] == "README.md"
    assert document_json["readme"]["applied"] is False
    assert [a["topic"] for a in document_json["ai"]["added"]] == [
        "installation",
        "usage",
        "tests",
    ]
    assert document_json["ai"]["creates"] is False
    assert document_json["ai"]["diff"].startswith("--- a/README.md\n")


def test_a_complete_readme_needs_no_ai_call(readme_repo, capsys, fake_readme_ai):
    write(readme_repo, "README.md", COMPLETE_README)

    assert write_readme(readme_repo) == EXIT_OK

    assert "README.md needs no section DevAI can ask for. Nothing was sent." in (
        capsys.readouterr().out
    )
    assert fake_readme_ai.requests == []


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--readme"], "--readme requires --ai"),
        (["--ai", "--readme", "--file", "stats.js"], "use --file or --readme"),
        (["--ai"], "--ai needs the file to document (--file PATH) or --readme"),
    ],
)
def test_readme_usage_errors(readme_repo, capsys, fake_readme_ai, args, message):
    assert main(["docs", str(readme_repo), *args]) == EXIT_USAGE

    assert message in capsys.readouterr().err
    assert fake_readme_ai.requests == []


def test_a_readme_that_is_not_markdown_is_refused(git_repo, capsys, fake_readme_ai):
    write(git_repo, "README.rst", "Stats\n=====\n")

    assert write_readme(git_repo) == EXIT_USAGE
    assert "only Markdown READMEs can be extended" in capsys.readouterr().err
