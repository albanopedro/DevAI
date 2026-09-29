import subprocess
import sys

import pytest

from devai import __version__
from devai.cli import EXIT_BAD_PATH, EXIT_OK, EXIT_USAGE, main


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
    project.mkdir()
    (project / "README.md").write_text("# Demo")
    (project / "main.py").write_text("print('hi')")

    (project / "src").mkdir()
    for name in ["app.py", "util.py", "index.js"]:
        (project / "src" / name).write_text("x")

    assert main(["analyze", str(project)]) == EXIT_OK

    assert capsys.readouterr().out == (
        "DEVAI ANALYSIS\n"
        "────────────────────────────────────\n"
        "Project:        demo\n"
        f"Path:           {project.resolve()}\n"
        "Files:          5 (filesystem)\n"
        "Git repository: no\n"
        "README:         yes\n"
        "\n"
        "Languages:\n"
        "  Python      3 files   75%\n"
        "  JavaScript  1 file    25%\n"
        "\n"
        "Structure:\n"
        "  src/    3 files\n"
        "  (root)  2 files\n"
    )


def test_analyze_empty_directory(tmp_path, capsys):
    assert main(["analyze", str(tmp_path)]) == EXIT_OK

    out = capsys.readouterr().out
    assert "Files:          0 (filesystem)" in out
    assert "Languages:\n  none detected" in out
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

    assert main(["analyze", str(missing)]) == EXIT_BAD_PATH

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
