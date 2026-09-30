"""Run every check against a ProjectInfo and collect the results."""

from devai.checks.project_checks import PROJECT_CHECKS
from devai.checks.secrets import check_secrets
from devai.models import CheckReport, Finding, ProjectInfo


def run_checks(info: ProjectInfo) -> CheckReport:
    results = [check(info) for check in PROJECT_CHECKS]
    secrets_result, secret_scan = check_secrets(info)
    results.append(secrets_result)

    findings = [finding for result in results for finding in result.findings]
    return CheckReport(
        findings=tuple(sorted(findings, key=severity_then_location)),
        passed=tuple(r.passed_message for r in results if r.passed_message),
        secret_scan=secret_scan,
    )


def severity_then_location(finding: Finding) -> tuple[int, str, int]:
    """Most severe first; then project-level findings, then by file and line."""
    return (-finding.severity.rank, str(finding.file or ""), finding.line or 0)
