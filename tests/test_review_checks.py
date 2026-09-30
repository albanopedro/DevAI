from pathlib import Path, PurePosixPath

from conftest import FAKE_SECRETS

from devai.models import ChangedFile, Severity
from devai.review.checks import (
    check_change_size,
    check_debug_statements,
    check_env_files,
    check_secrets,
    check_tests_changed,
    run_review_checks,
)
from devai.review.diff import AddedLine, Changes


def changes(files=(), added=None, skipped=()):
    return Changes(
        root=Path("/repo"),
        description="test",
        files=tuple(files),
        added_lines={
            PurePosixPath(path): tuple(
                AddedLine(number, text) for number, text in enumerate(lines, start=1)
            )
            for path, lines in (added or {}).items()
        },
        skipped=tuple(PurePosixPath(path) for path in skipped),
    )


def changed(path, status="M", additions=1, deletions=0):
    return ChangedFile(PurePosixPath(path), status, additions, deletions)


# --- secrets ------------------------------------------------------------------


def test_secret_in_an_added_line_is_high_and_masked():
    secret, prefix = FAKE_SECRETS["secret/aws-access-key"]
    result = check_secrets(
        changes([changed("config.ts")], {"config.ts": ["// ok", f"key = '{secret}'"]})
    )

    [finding] = result.findings
    assert finding.severity is Severity.HIGH
    assert (str(finding.file), finding.line) == ("config.ts", 2)
    assert finding.evidence == prefix
    assert secret not in repr(finding)


def test_generic_credentials_are_ignored_in_test_files():
    line = ['password = "s3cr3tValue"']
    in_test = changes([changed("tests/test_login.py")], {"tests/test_login.py": line})
    in_code = changes([changed("login.py")], {"login.py": line})

    assert check_secrets(in_test).findings == ()
    assert len(check_secrets(in_code).findings) == 1


# --- .env files ---------------------------------------------------------------


def test_env_file_in_the_changes_is_high():
    result = check_env_files(changes([changed(".env"), changed("app/.env.production")]))

    assert [str(finding.file) for finding in result.findings] == [
        ".env",
        "app/.env.production",
    ]
    assert all(finding.severity is Severity.HIGH for finding in result.findings)


def test_deleting_env_or_changing_templates_is_fine():
    result = check_env_files(
        changes([changed(".env", status="D"), changed(".env.example")])
    )

    assert result.findings == ()


# --- tests changed --------------------------------------------------------------


def test_code_without_test_changes_is_medium():
    [finding] = check_tests_changed(
        changes([changed("src/app.py"), changed("README.md")])
    ).findings

    assert finding.severity is Severity.MEDIUM
    assert "Code changed in 1 file(s)" in finding.message


def test_code_with_test_changes_passes():
    result = check_tests_changed(
        changes([changed("src/app.py"), changed("tests/test_app.py")])
    )

    assert result.passed_message == "Tests changed along with the code"


def test_docs_only_changes_do_not_ask_for_tests():
    result = check_tests_changed(changes([changed("README.md"), changed("docs/a.md")]))

    assert result.findings == () and result.passed_message is None


# --- debug statements -----------------------------------------------------------


def test_debug_statements_are_grouped_per_file():
    # Built at runtime so this test file doesn't contain the statements itself.
    call = "console" + ".log"
    lines = ["let a = 1", f"{call}(a)", "let b = 2", f"{call}(b)"]
    python = ["x = 1", "breakpoint" + "()", "import " + "pdb"]

    result = check_debug_statements(
        changes(
            [changed("app.js"), changed("tool.py")],
            {"app.js": lines, "tool.py": python},
        )
    )

    by_file = {str(finding.file): finding for finding in result.findings}
    assert by_file["app.js"].message == "Debug statement added (2 in this file)"
    assert (by_file["app.js"].line, by_file["app.js"].evidence) == (2, "console.log")
    assert by_file["tool.py"].line == 2
    assert all(f.severity is Severity.LOW for f in result.findings)


def test_words_that_only_look_like_debug_calls_are_fine():
    lines = ["# we removed the debugger statement", "log = console_logger()"]

    result = check_debug_statements(changes([changed("a.js")], {"a.js": lines}))

    assert result.findings == ()


# --- size -----------------------------------------------------------------------


def test_large_change_is_low():
    [finding] = check_change_size(
        changes([changed("a.py", additions=400, deletions=150)])
    ).findings

    assert finding.severity is Severity.LOW
    assert "550 lines changed" in finding.message


def test_small_change_passes():
    result = check_change_size(changes([changed("a.py", additions=10, deletions=5)]))

    assert result.passed_message == "Change size is reviewable (15 lines)"


def test_binary_files_do_not_count_lines():
    result = check_change_size(changes([changed("a.png", additions=None)]))

    assert result.passed_message == "Change size is reviewable (0 lines)"


# --- all together ---------------------------------------------------------------


def test_no_changes_means_nothing_to_judge():
    report = run_review_checks(changes())

    assert report.findings == () and report.passed == ()


def test_findings_are_sorted_by_severity():
    secret, _ = FAKE_SECRETS["secret/github-token"]
    report = run_review_checks(
        changes(
            [changed("src/app.py"), changed(".env")],
            {"src/app.py": [f"t = '{secret}'"]},
            skipped=[".env"],
        )
    )

    assert [f.severity for f in report.findings] == [
        Severity.HIGH,
        Severity.HIGH,
        Severity.MEDIUM,
    ]
    assert (report.secret_scan.scanned, report.secret_scan.skipped) == (1, 1)
