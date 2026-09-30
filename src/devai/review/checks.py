"""Checks on the changes: they look only at added lines and file names."""

import re
from collections.abc import Callable
from dataclasses import replace

from devai.analyzer.languages import language_for
from devai.analyzer.testing import is_test_file
from devai.checks.result import CheckResult, failing, passing
from devai.checks.runner import severity_then_location
from devai.checks.secrets import is_real_env_file, match_line
from devai.models import CheckReport, Finding, SecretScanStats, Severity
from devai.review.diff import Changes

LARGE_CHANGE_LINES = 500

# Leftovers from debugging, by the label shown as evidence. Labels carry no call
# syntax, so this file never matches its own patterns.
DEBUG_STATEMENTS = {
    "console.log": re.compile(r"\bconsole\.log\s*\("),
    "debugger": re.compile(r"^\s*debugger\s*;?\s*$"),
    "breakpoint": re.compile(r"\bbreakpoint\(\s*\)"),
    "pdb": re.compile(r"\bpdb\.set_trace\(\s*\)|^\s*import\s+pdb\b"),
}


def check_secrets(changes: Changes) -> CheckResult:
    findings = []
    for path, lines in changes.added_lines.items():
        # Tests are full of fake passwords; only the precise rules apply there.
        include_generic = not is_test_file(path)
        for line in lines:
            finding = match_line(line.text, include_generic)
            if finding is not None:
                findings.append(replace(finding, file=path, line=line.number))
    if findings:
        return failing(*findings)
    return passing("No known secret patterns in added lines")


def check_env_files(changes: Changes) -> CheckResult:
    findings = [
        Finding(
            "review/env-file",
            Severity.HIGH,
            "Environment file in the changes: its values would be committed",
            file=file.path,
        )
        for file in changes.files
        if file.status != "D" and is_real_env_file(file.path)
    ]
    if findings:
        return failing(*findings)
    return passing("No .env files in the changes")


def check_tests_changed(changes: Changes) -> CheckResult:
    code = [file for file in changes.files if language_for(file.path)]
    source = [file for file in code if not is_test_file(file.path)]
    if not source:
        return CheckResult()  # only docs, configs or tests changed: nothing to ask
    if any(is_test_file(file.path) for file in code):
        return passing("Tests changed along with the code")
    return failing(
        Finding(
            "review/no-test-changes",
            Severity.MEDIUM,
            f"Code changed in {len(source)} file(s) but no tests changed",
        )
    )


def check_debug_statements(changes: Changes) -> CheckResult:
    findings = []
    for path, lines in changes.added_lines.items():
        hits = [
            (line, label)
            for line in lines
            for label, pattern in DEBUG_STATEMENTS.items()
            if pattern.search(line.text)
        ]
        if hits:
            first_line, label = hits[0]
            extra = f" ({len(hits)} in this file)" if len(hits) > 1 else ""
            findings.append(
                Finding(
                    "review/debug-statement",
                    Severity.LOW,
                    f"Debug statement added{extra}",
                    file=path,
                    line=first_line.number,
                    evidence=label,
                )
            )
    if findings:
        return failing(*findings)
    return passing("No debug statements added")


def check_change_size(changes: Changes) -> CheckResult:
    total = changed_lines(changes)
    if total > LARGE_CHANGE_LINES:
        return failing(
            Finding(
                "review/large-change",
                Severity.LOW,
                f"Large change: {total} lines changed. Consider splitting it",
            )
        )
    return passing(f"Change size is reviewable ({total} lines)")


def changed_lines(changes: Changes) -> int:
    return sum((file.additions or 0) + (file.deletions or 0) for file in changes.files)


REVIEW_CHECKS: tuple[Callable[[Changes], CheckResult], ...] = (
    check_secrets,
    check_env_files,
    check_tests_changed,
    check_debug_statements,
    check_change_size,
)


def run_review_checks(changes: Changes) -> CheckReport:
    if not changes.files:
        return CheckReport()  # nothing changed: nothing to judge

    results = [check(changes) for check in REVIEW_CHECKS]
    findings = [finding for result in results for finding in result.findings]
    return CheckReport(
        findings=tuple(sorted(findings, key=severity_then_location)),
        passed=tuple(r.passed_message for r in results if r.passed_message),
        secret_scan=SecretScanStats(
            scanned=len(changes.added_lines), skipped=len(changes.skipped)
        ),
    )
