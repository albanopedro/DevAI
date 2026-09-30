"""The outcome of a single check."""

from dataclasses import dataclass

from devai.models import Finding


@dataclass(frozen=True)
class CheckResult:
    findings: tuple[Finding, ...] = ()
    passed_message: str | None = None  # None: failed, or check didn't apply


def passing(message: str) -> CheckResult:
    return CheckResult(passed_message=message)


def failing(*findings: Finding) -> CheckResult:
    return CheckResult(findings=findings)
