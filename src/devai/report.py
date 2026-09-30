"""Render analysis results as human-readable terminal text."""

import textwrap

from devai.ai.result import AIResult
from devai.models import CheckReport, Finding, Manifest, ProjectInfo, TestSummary

SEPARATOR = "─" * 36
TEXT_WIDTH = 88


def format_report(info: ProjectInfo, checks: CheckReport) -> str:
    lines = [
        "DEVAI ANALYSIS",
        SEPARATOR,
        f"Project:        {info.name}",
        f"Path:           {info.path}",
        f"Files:          {info.file_count} ({info.file_source})",
        f"Git repository: {yes_no(info.has_git)}",
        f"README:         {yes_no(info.has_readme)}",
        "",
        "Languages:",
        *format_languages(info),
        "",
        "Frameworks:",
        f"  {', '.join(info.frameworks) or 'none detected'}",
        "",
        "Dependencies:",
        *format_manifests(info),
        "",
        "Tests:",
        f"  {describe_tests(info.tests)}",
        "",
        "Configuration:",
        *(f"  {path}" for path in info.config_files or ["none detected"]),
        "",
        "Structure:",
        *format_structure(info),
        "",
        "Findings:",
        *format_findings(checks.findings),
        "",
        "Passed:",
        *([f"  ✓ {message}" for message in checks.passed] or ["  none"]),
        "",
        f"Secrets scan: {checks.secret_scan.scanned} files scanned, "
        f"{checks.secret_scan.skipped} skipped",
    ]
    if info.warnings:
        lines += ["", "Warnings:", *(f"  ! {warning}" for warning in info.warnings)]
    return "\n".join(lines)


def format_languages(info: ProjectInfo) -> list[str]:
    if not info.languages:
        return ["  none detected"]

    total = sum(language.files for language in info.languages)
    rows = [
        (language.name, language.files, f"{round(100 * language.files / total)}%")
        for language in info.languages
    ]
    return format_rows(rows)


def format_manifests(info: ProjectInfo) -> list[str]:
    if not info.manifests:
        return ["  none detected"]

    width = max(len(str(manifest.path)) for manifest in info.manifests)
    return [
        f"  {str(manifest.path):<{width}}  {describe_manifest(manifest)}"
        for manifest in info.manifests
    ]


def describe_manifest(manifest: Manifest) -> str:
    if not manifest.parsed:
        return "found, not parsed"
    dev = sum(1 for dependency in manifest.dependencies if dependency.dev)
    runtime = len(manifest.dependencies) - dev
    return f"{runtime} runtime, {dev} dev"


def describe_tests(tests: TestSummary) -> str:
    frameworks = ", ".join(tests.frameworks)
    if tests.files:
        count = f"{tests.files} {plural(tests.files, 'file')}"
        return f"{count} ({frameworks})" if frameworks else count
    if frameworks:
        return f"no test files found ({frameworks} in dependencies)"
    return "none detected"


def format_findings(findings: tuple[Finding, ...]) -> list[str]:
    if not findings:
        return ["  none"]

    lines = []
    for finding in findings:
        title = finding.message
        if finding.evidence:
            title += f" ({finding.evidence})"
        lines.append(f"  ⚠ {finding.severity.upper():<6}  {title}")
        if finding.file:
            location = (
                f"{finding.file}:{finding.line}" if finding.line else finding.file
            )
            lines.append(f"{'':12}{location}")  # aligned under the title
    return lines


def format_structure(info: ProjectInfo) -> list[str]:
    rows = [
        (f"{directory.name}/", directory.files, "") for directory in info.directories
    ]
    if info.root_file_count:
        rows.append(("(root)", info.root_file_count, ""))
    if not rows:
        return ["  empty"]
    return format_rows(rows)


def format_rows(rows: list[tuple[str, int, str]]) -> list[str]:
    """Align (label, file count, extra) rows into columns."""
    label_width = max(len(label) for label, _, _ in rows)
    count_width = max(len(str(count)) for _, count, _ in rows)
    return [
        # Pad "file" to the width of "files" so the extra column stays aligned.
        f"  {label:<{label_width}}  {count:>{count_width}} "
        f"{plural(count, 'file'):<5}  {extra:>4}".rstrip()
        for label, count, extra in rows
    ]


def plural(count: int, word: str) -> str:
    return word if count == 1 else f"{word}s"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def format_ai_section(result: AIResult) -> str:
    """Render the AI's report. Every string in it is model output: untrusted."""
    report = result.report
    lines = [f"AI ANALYSIS ({printable(result.model)})", SEPARATOR, "Summary:"]
    lines += wrap(report.summary, "  ")

    lines += ["", "Risks:"]
    for risk in report.risks:
        lines.append(f"  ⚠ {risk.severity.upper():<6}  {printable(risk.title)}")
        lines += wrap(risk.explanation, " " * 12)
        if risk.related_rule:
            lines.append(f"{'':12}related finding: {printable(risk.related_rule)}")
    if not report.risks:
        lines.append("  none")

    lines += ["", "Recommendations:"]
    for number, item in enumerate(report.recommendations, start=1):
        lines.append(f"  {number}. {printable(item.title)} [{item.effort} effort]")
        lines += wrap(item.rationale, "     ")
    if not report.recommendations:
        lines.append("  none")

    lines += ["", "Limitations:"]
    for limitation in report.limitations:
        lines += wrap(limitation, "  - ", "    ")
    if not report.limitations:
        lines.append("  none")

    usage = result.usage
    lines += [
        "",
        f"Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out",
        "Written by AI from a summary of the project, without reading its code.",
    ]
    return "\n".join(lines)


def wrap(text: str, indent: str, subsequent_indent: str | None = None) -> list[str]:
    return textwrap.wrap(
        printable(text),
        width=TEXT_WIDTH,
        initial_indent=indent,
        subsequent_indent=indent if subsequent_indent is None else subsequent_indent,
    )


def printable(text: str) -> str:
    """Replace control characters (newlines, ANSI escape codes...) with spaces.

    Model output is untrusted: an escape sequence could rewrite the terminal.
    """
    return "".join(char if char.isprintable() else " " for char in text)
