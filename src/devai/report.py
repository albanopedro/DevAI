"""Render analysis results as human-readable terminal text."""

import textwrap

from devai.ai.result import AIResult
from devai.models import (
    ChangedFile,
    CheckReport,
    Finding,
    Manifest,
    ProjectInfo,
    ReviewReport,
    TestSummary,
)

SEPARATOR = "─" * 36
TEXT_WIDTH = 88
MAX_LISTED_FILES = 50  # the JSON output lists every file


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


def format_review(report: ReviewReport) -> str:
    """Render `devai review`. Only names, counts and findings: never code."""
    files = report.files
    added = sum(file.additions or 0 for file in files)
    deleted = sum(file.deletions or 0 for file in files)
    lines = [
        "DEVAI REVIEW",
        SEPARATOR,
        f"Project:  {report.name}",
        f"Changes:  {report.description}",
    ]
    if not files:
        lines += ["", "No changes to review."]
        return "\n".join(lines)

    lines.append(f"Files:    {len(files)} changed (+{added} -{deleted})")
    lines += format_changed_files(files)
    checks = report.checks
    lines += [
        "",
        "Findings:",
        *format_findings(checks.findings),
        "",
        "Passed:",
        *([f"  ✓ {message}" for message in checks.passed] or ["  none"]),
        "",
        f"Content checked: {checks.secret_scan.scanned} files, "
        f"{checks.secret_scan.skipped} not read (env, lock, binary, large)",
    ]
    return "\n".join(lines)


def format_changed_files(files: tuple[ChangedFile, ...]) -> list[str]:
    shown = files[:MAX_LISTED_FILES]
    names = [describe_path(file) for file in shown]
    width = max(len(name) for name in names)
    lines = [
        f"  {file.status}  {name:<{width}}  {describe_counts(file)}".rstrip()
        for file, name in zip(shown, names, strict=True)
    ]
    if len(files) > len(shown):
        lines.append(f"  … and {len(files) - len(shown)} more (see --format json)")
    return lines


def describe_path(file: ChangedFile) -> str:
    name = printable(str(file.path))  # file names come from the project: untrusted
    if file.old_path:
        name = f"{printable(str(file.old_path))} → {name}"
    return f"{name} (untracked)" if file.untracked else name


def describe_counts(file: ChangedFile) -> str:
    if file.additions is None:
        return "not counted"
    parts = []
    if file.additions:
        parts.append(f"+{file.additions}")
    if file.deletions:
        parts.append(f"-{file.deletions}")
    return " ".join(parts)


def format_ai_review_section(result: AIResult, discarded: int = 0) -> str:
    """Render the AI review. Every string in it is model output: untrusted."""
    report = result.report
    lines = [f"AI REVIEW ({printable(result.model)})", SEPARATOR, "Summary:"]
    lines += wrap(report.summary, "  ")

    lines += ["", "Issues:"]
    for issue in report.issues:
        title = f"[{printable(issue.category)}] {printable(issue.title)}"
        lines.append(f"  ⚠ {issue.severity.upper():<6}  {title}")
        location = printable(issue.file)
        if issue.line is not None:
            location += f":{issue.line}"
        lines.append(f"{'':12}{location}")
        lines += wrap(issue.explanation, " " * 12)
        lines += wrap(f"Suggestion: {issue.suggestion}", " " * 12)
    if not report.issues:
        lines.append("  none")

    lines += ["", "Suggested tests:"]
    for test in report.suggested_tests:
        lines += wrap(test, "  - ", "    ")
    if not report.suggested_tests:
        lines.append("  none")

    lines += ["", "Limitations:"]
    for limitation in report.limitations:
        lines += wrap(limitation, "  - ", "    ")
    if not report.limitations:
        lines.append("  none")

    lines.append("")
    if discarded:
        noun = "issue" if discarded == 1 else "issues"
        lines.append(
            f"Discarded {discarded} {noun} about files whose code the AI didn't see."
        )
    usage = result.usage
    lines += [
        f"Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out",
        "Written by AI from the changed lines only, not the whole project.",
    ]
    return "\n".join(lines)


def format_chat_header(name: str, context: dict) -> str:
    """The question and the files that would go with it (names and reasons only)."""
    lines = [
        "DEVAI CHAT",
        SEPARATOR,
        f"Project:  {printable(name)}",
        f"Question: {printable(context['question'])}",
    ]
    return "\n".join(lines + format_chat_files(context))


def format_chat_files(context: dict) -> list[str]:
    files = context["files"]
    if not files:
        return ["Files:    none; only the project summary goes with the question"]
    width = max(len(printable(file["path"])) for file in files)
    return ["Files:"] + [
        f"  {number}. {printable(file['path']):<{width}}  "
        f"{printable(file['reason'])}  ({len(file['lines'])} "
        f"{plural(len(file['lines']), 'line')})"
        for number, file in enumerate(files, start=1)
    ]


def format_chat_answer(
    result: AIResult, dropped_sources: int = 0, dropped_suggestions: int = 0
) -> str:
    """Render a chat answer. Every string in it is model output: untrusted."""
    answer = result.report
    lines = [f"ANSWER ({printable(result.model)})", SEPARATOR]
    # Keep the answer's own line breaks (lists, code blocks); strip control chars.
    lines += [printable(line) for line in answer.answer.strip().split("\n")]

    if answer.sources:
        lines += ["", "Sources:"]
        lines += [f"  {printable(source)}" for source in answer.sources]
    if answer.suggested_files:
        lines += ["", "The AI would also like to see (add them with --file or /add):"]
        for suggestion in answer.suggested_files:
            lines += wrap(f"{suggestion.path}: {suggestion.reason}", "  - ", "    ")

    dropped = []
    if dropped_sources:
        dropped.append(f"{dropped_sources} {plural(dropped_sources, 'source')}")
    if dropped_suggestions:
        dropped.append(
            f"{dropped_suggestions} {plural(dropped_suggestions, 'suggestion')}"
        )
    lines.append("")
    if dropped:
        lines.append(
            f"Dropped {' and '.join(dropped)} that didn't match the shown files "
            "or the project."
        )
    usage = result.usage
    lines += [
        f"Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out",
        "Written by AI from the files listed above, not the whole project.",
    ]
    return "\n".join(lines)
