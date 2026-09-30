import json
import subprocess
import sys

import pytest
from conftest import FAKE_SECRETS, make_files

from devai import __version__
from devai.cli import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE, main


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
