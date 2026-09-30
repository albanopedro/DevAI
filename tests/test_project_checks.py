from conftest import git_add, make_files

from devai.analyzer import analyze_project
from devai.checks import run_checks
from devai.checks.project_checks import (
    check_env_files,
    check_gitignore,
    check_readme,
    check_tests,
)
from devai.models import Severity


def rule_ids(result):
    return [finding.rule_id for finding in result.findings]


def test_readme(tmp_path):
    assert rule_ids(check_readme(analyze_project(tmp_path))) == ["no-readme"]

    make_files(tmp_path, "README.md")
    result = check_readme(analyze_project(tmp_path))
    assert result.findings == ()
    assert result.passed_message == "README found"


def test_gitignore(tmp_path):
    assert rule_ids(check_gitignore(analyze_project(tmp_path))) == ["no-gitignore"]

    make_files(tmp_path, ".gitignore")
    assert check_gitignore(analyze_project(tmp_path)).findings == ()


def test_gitignore_at_repository_root_counts_for_subdirectories(git_repo):
    make_files(git_repo, ".gitignore", "api/app.py")

    assert check_gitignore(analyze_project(git_repo / "api")).findings == ()


def test_missing_tests_is_medium(tmp_path):
    make_files(tmp_path, "app.py")

    [finding] = check_tests(analyze_project(tmp_path)).findings

    assert (finding.rule_id, finding.severity) == ("no-tests", Severity.MEDIUM)


def test_tests_found(tmp_path):
    make_files(tmp_path, "app.py", "tests/test_app.py")

    result = check_tests(analyze_project(tmp_path))

    assert result.passed_message == "Tests found (1 file)"


def test_tests_check_does_not_apply_without_source_code(tmp_path):
    make_files(tmp_path, "README.md")

    result = check_tests(analyze_project(tmp_path))

    assert result.findings == ()
    assert result.passed_message is None


def test_exposed_env_file_is_high(tmp_path):
    make_files(tmp_path, "backend/.env", ".env.example")

    [finding] = check_env_files(analyze_project(tmp_path)).findings

    assert finding.rule_id == "env-not-ignored"
    assert finding.severity is Severity.HIGH
    assert str(finding.file) == "backend/.env"


def test_git_ignored_env_file_is_fine(git_repo):
    make_files(git_repo, ".gitignore", ".env")
    (git_repo / ".gitignore").write_text(".env\n")

    assert check_env_files(analyze_project(git_repo)).findings == ()


def test_tracked_env_file_is_reported_even_if_ignored_later(git_repo):
    make_files(git_repo, ".env")
    git_add(git_repo, ".env")
    (git_repo / ".gitignore").write_text(".env\n")

    [finding] = check_env_files(analyze_project(git_repo)).findings

    assert "tracked or not ignored" in finding.message


def test_run_checks_sorts_by_severity_and_collects_passed(tmp_path):
    make_files(tmp_path, "app.py", ".env")

    report = run_checks(analyze_project(tmp_path))

    assert [finding.rule_id for finding in report.findings] == [
        "env-not-ignored",
        "no-tests",
        "no-readme",  # same severity: sorted() is stable, so check order stays
        "no-gitignore",
    ]
    assert report.passed == ("No known secret patterns found",)
