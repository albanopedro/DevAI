import io
import json
import subprocess
import sys

import pytest
from conftest import (
    FAKE_SECRETS,
    fake_ai_report,
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


# --- AI (Phase 3a: dry run only) ---------------------------------------------


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


# --- AI (Phase 3b): the model is always a fake here, never the network -------


class FakeLLMClient:
    def __init__(self, result=None, error=None):
        self.contexts = []
        self.result = result or AIResult(
            fake_ai_report(), "fake-model", AIUsage(10, 20)
        )
        self.error = error

    def analyze(self, context):
        self.contexts.append(context)
        if self.error:
            raise self.error
        return self.result


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


# --- providers (Phase 3.5) ---------------------------------------------------


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


# --- review (Phase 4a) ---------------------------------------------------------


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
