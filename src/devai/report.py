"""Render analysis results as human-readable terminal text."""

import shlex
import textwrap

from devai.ai.result import AIResult
from devai.docmap import MODULE
from devai.docmap.readme import MARKDOWN_SUFFIXES
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


def format_fix_header(name: str, context: dict) -> str:
    lines = [
        "DEVAI FIX",
        SEPARATOR,
        f"Project: {printable(name)}",
        f"Request: {printable(context['request'])}",
        "Files the fix may change:",
        *(f"  {printable(file['path'])}" for file in context["files"]),
    ]
    return "\n".join(lines)


def format_fix_proposal(result: AIResult, changes: list, applying: bool = False) -> str:
    """Render a validated proposal and its diff. Model output: untrusted."""
    proposal = result.report
    lines = [f"PROPOSED FIX ({printable(result.model)})", SEPARATOR, "Summary:"]
    lines += wrap(proposal.summary, "  ")

    lines += ["", "Changes:"]
    if changes:
        for change in changes:
            # The diff keeps its own lines; only control characters are removed.
            lines += [printable(line) for line in change.diff.rstrip("\n").split("\n")]
    else:
        lines.append("  none: the AI proposed no change")

    lines += ["", "Risks:"]
    lines += [line for risk in proposal.risks for line in wrap(risk, "  - ", "    ")]
    if not proposal.risks:
        lines.append("  none listed")
    lines += ["", "How to verify:"]
    lines += [line for test in proposal.tests for line in wrap(test, "  - ", "    ")]
    if not proposal.tests:
        lines.append("  none listed")

    usage = result.usage
    lines.append("")
    if not applying:
        lines.append("Nothing was changed. To write this fix, run again with --apply.")
    lines += [
        f"Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out",
        "Written by AI. Review the diff before applying anything.",
    ]
    return "\n".join(lines)


def format_fix_applied(changes: list, tests: list[str]) -> str:
    """What was written, how to undo it, and how to verify it (never executed)."""
    paths = " ".join(shlex.quote(printable(str(change.path))) for change in changes)
    lines = [
        "",
        f"Applied to {', '.join(str(change.path) for change in changes)}.",
        f"Undo with: git restore {paths}",
    ]
    if tests:
        lines.append("Verify with (DevAI doesn't run these):")
        lines += [line for test in tests for line in wrap(test, "  - ", "    ")]
    lines.append("Nothing was committed.")
    return "\n".join(lines)


MAX_LISTED_UNTESTED = 30


def format_coverage_map(name: str, coverage) -> str:
    """Render `devai test`: an estimate of where tests are missing."""
    if coverage.test_files:
        frameworks = ", ".join(coverage.frameworks)
        tests = f"{coverage.test_files} {plural(coverage.test_files, 'file')}"
        tests += f" ({frameworks})" if frameworks else ""
    else:
        tests = "none found"
    languages = ", ".join(coverage.languages) or "none"
    lines = [
        "DEVAI TEST",
        SEPARATOR,
        f"Project:  {printable(name)}",
        f"Tests:    {tests}",
        f"Source:   {coverage.sources_checked} "
        f"{plural(coverage.sources_checked, 'file')} checked ({languages})",
        "",
    ]

    missing = coverage.without_tests
    if missing:
        lines.append(f"Without a matching test file ({len(missing)}):")
        lines += [f"  {printable(str(path))}" for path in missing[:MAX_LISTED_UNTESTED]]
        if len(missing) > MAX_LISTED_UNTESTED:
            lines.append(
                f"  … and {len(missing) - MAX_LISTED_UNTESTED} more (see --format json)"
            )
    elif coverage.sources_checked:
        lines.append("Every checked source file has a matching test file.")
    else:
        lines.append("No Python, JavaScript or TypeScript source files to check.")

    if coverage.untested_symbols:
        count = sum(len(symbols) for _, symbols in coverage.untested_symbols)
        files = len(coverage.untested_symbols)
        lines += [
            "",
            f"Python names no test mentions ({count} in {files} "
            f"{plural(files, 'file')}):",
        ]
        for path, symbols in coverage.untested_symbols[:MAX_LISTED_UNTESTED]:
            lines += wrap(f"{path}: {', '.join(symbols)}", "  ", "      ")
    if coverage.not_parsed:
        lines += [
            "",
            "Not parsed (invalid Python): "
            + ", ".join(printable(str(path)) for path in coverage.not_parsed),
        ]

    lines += [
        "",
        "An estimate from file and symbol names, not a coverage measurement:",
        "code tested indirectly (through other functions) can look untested.",
    ]
    return "\n".join(lines)


def format_testgen_header(name: str, context: dict) -> str:
    existing = [test["path"] for test in context["existing_tests"]]
    return "\n".join(
        [
            "DEVAI TESTS",
            SEPARATOR,
            f"Project:        {printable(name)}",
            f"Source:         {printable(context['source']['path'])}",
            f"Existing tests: {printable(', '.join(existing)) or 'none'}",
        ]
    )


def format_generated_tests(
    result: AIResult, path, command: str, applying: bool = False
) -> str:
    """Render the proposed test file. Model output: untrusted."""
    proposal = result.report
    lines = [f"PROPOSED TESTS ({printable(result.model)})", SEPARATOR]
    lines.append(f"New file: {printable(str(path))}")
    if proposal.covers:
        lines += wrap(f"Covers: {', '.join(proposal.covers)}", "", "        ")
    lines += ["", f"--- {printable(str(path))} (new file)"]
    lines += [printable(line) for line in proposal.content.rstrip("\n").split("\n")]
    if proposal.notes:
        lines += ["", "Notes:"]
        lines += [
            line for note in proposal.notes for line in wrap(note, "  - ", "    ")
        ]
    usage = result.usage
    lines += [
        "",
        f"Run them yourself with: {command}",
        "Tests are code: review them before running. DevAI doesn't run them.",
    ]
    if not applying:
        lines.append(
            "Nothing was created. To create this file, run again with --apply."
        )
    lines += [
        f"Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out",
        "Written by AI from the files listed above.",
    ]
    return "\n".join(lines)


def format_tests_created(path, undo: str, command: str) -> str:
    return "\n".join(
        [
            "",
            f"Created {printable(str(path))}.",
            f"Undo with: {undo}",
            f"Run them yourself with: {command}",
            "Nothing was committed.",
        ]
    )


MAX_LISTED_UNDOCUMENTED = 30


def format_docs_map(name: str, docs) -> str:
    """Render `devai docs`: where documentation seems to be missing."""
    languages = ", ".join(docs.languages) or "none"
    lines = [
        "DEVAI DOCS",
        SEPARATOR,
        f"Project:     {printable(name)}",
        f"Source:      {docs.sources_checked} "
        f"{plural(docs.sources_checked, 'file')} checked ({languages})",
        f"Documented:  {describe_documented(docs)}",
        "",
    ]

    missing = docs.undocumented
    if missing:
        count = sum(len(names) for _, names in missing)
        lines.append(
            f"Names without docs ({count} in {len(missing)} "
            f"{plural(len(missing), 'file')}):"
        )
        for path, names in missing[:MAX_LISTED_UNDOCUMENTED]:
            lines += wrap(f"{path}: {', '.join(names)}", "  ", "      ")
        if len(missing) > MAX_LISTED_UNDOCUMENTED:
            lines.append(
                f"  … and {len(missing) - MAX_LISTED_UNDOCUMENTED} more files "
                "(see --format json)"
            )
        if any(MODULE in names for _, names in missing):
            lines.append(f"  {MODULE}: the file has no module docstring.")
    elif docs.public_names:
        lines.append("Every public name checked has docs.")
    elif not docs.sources_checked:
        lines.append("No Python, JavaScript or TypeScript source files to check.")
    if docs.not_parsed:
        lines += [
            "",
            "Not parsed (invalid Python): "
            + ", ".join(printable(str(path)) for path in docs.not_parsed),
        ]

    lines += ["", *format_readme_map(docs.readme)]
    lines += [
        "",
        "An estimate: Python is parsed, JavaScript and TypeScript exports are found",
        "by pattern, and only /** */ counts as JSDoc. Not every name needs docs: use",
        "it to choose where to look. README sections are found by heading words.",
    ]
    return "\n".join(lines)


def describe_documented(docs) -> str:
    if not docs.public_names:
        return "no public functions or classes found"
    percent = round(100 * docs.documented / docs.public_names)
    return (
        f"{docs.documented} of {docs.public_names} public "
        f"{plural(docs.public_names, 'name')} ({percent}%)"
    )


def format_readme_map(readme) -> list[str]:
    if readme is None:
        return ["README: none found at the project root."]
    path = printable(str(readme.path))
    if not readme.checked:
        reason = (
            "too large or not text"
            if readme.path.suffix.lower() in MARKDOWN_SUFFIXES
            else "only Markdown READMEs are read"
        )
        return [f"{path}: not checked ({reason})."]

    found = [
        f"license ({printable(str(readme.license_file))} file)"
        if section == "license" and readme.license_file is not None
        else section
        for section in readme.sections
    ]
    lines = [
        f"{path}:",
        f"  Sections found:    {', '.join(found) or 'none'}",
        f"  Sections missing:  {', '.join(readme.missing_sections) or 'none'}",
    ]
    mentioned = readme.scripts_mentioned
    if mentioned and not readme.scripts_checked:
        lines.append(
            "  npm scripts:       not checked (a package.json couldn't be read)"
        )
    elif readme.missing_scripts:
        lines.append(
            f"  npm scripts it runs that no package.json has "
            f"({len(readme.missing_scripts)}):"
        )
        lines += [
            f"    {printable(mention.command)}  (line {mention.line})"
            for mention in readme.missing_scripts
        ]
    elif mentioned:
        found_in = "found" if mentioned == 1 else "all found"
        lines.append(
            f"  npm scripts:       {mentioned} mentioned, {found_in} in package.json"
        )
    return lines


def format_docs_header(name: str, context: dict) -> str:
    file = context["file"]
    lines = [
        "DEVAI DOCS",
        SEPARATOR,
        f"Project:  {printable(name)}",
        f"File:     {printable(file['path'])} ({file['language']})",
    ]
    lines += wrap(f"Names:    {', '.join(context['names'])}", "", "          ")
    names = context["truncated"].get("names")
    if names:
        lines.append(
            f"          (the first {names['shown']} of {names['total']}; "
            "run again for the rest)"
        )
    return "\n".join(lines)


def format_nothing_to_document(path, targets: list) -> str:
    """Why no AI call is needed for this file."""
    inline = [target.name for target in targets if target.inline]
    if len(inline) < len(targets):
        return (
            f"The names without docs in {printable(str(path))} are past the lines "
            "DevAI sends. Nothing was sent."
        )
    if inline:
        return (
            f"Nothing to document in {printable(str(path))} that DevAI can place: "
            f"{', '.join(inline)} {'has' if len(inline) == 1 else 'have'} the body "
            "on the definition's line. Nothing was sent."
        )
    return f"Every public name in {printable(str(path))} has docs. Nothing was sent."


def format_doc_proposal(result: AIResult, plan, applying: bool = False) -> str:
    """Render the placed docs as a diff. Model output: untrusted."""
    lines = [f"PROPOSED DOCS ({printable(result.model)})", SEPARATOR]
    change = plan.change
    if change is not None:
        # The diff keeps its own lines; only control characters are removed.
        lines += [printable(line) for line in change.diff.rstrip("\n").split("\n")]
        lines += ["", f"Added:  {', '.join(plan.added)}"]
    else:
        lines.append("No usable docs in the answer: nothing to add.")
    if plan.dropped:
        lines += ["", f"Not used ({len(plan.dropped)}):"]
        lines += [
            line
            for name, why in plan.dropped
            for line in wrap(f"{name}: {why}", "  - ", "    ")
        ]
    if change is not None:
        lines.append("")
        if change.path.suffix == ".py":
            lines += [
                "Only documentation changed: checked. Without docstrings, the code",
                "parses to exactly the same syntax tree as before.",
            ]
        else:
            lines += [
                "Only documentation changed: checked. Each addition is a single",
                "/** */ comment right above an export, with no code in it.",
            ]

    notes = result.report.notes
    if notes:
        lines += ["", "Notes from the AI:"]
        lines += [line for note in notes for line in wrap(note, "  - ", "    ")]

    usage = result.usage
    lines.append("")
    if change is None:
        lines.append("Nothing was changed.")
    elif not applying:
        lines.append(
            "Nothing was changed. To write these docs, run again with --apply."
        )
    lines += [
        f"Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out",
        "Written by AI. Read it before applying: docs can be wrong about the code.",
    ]
    return "\n".join(lines)


def format_readme_header(name: str, context: dict, left_out: list) -> str:
    readme = context["readme"]
    shown = "none yet: a new README.md"
    if readme["exists"]:
        shown = printable(readme["path"])
    lines = [
        "DEVAI README",
        SEPARATOR,
        f"Project:  {printable(name)}",
        f"README:   {shown}",
        f"Topics:   {', '.join(context['topics'])}",
    ]
    lines += format_left_out(left_out)
    return "\n".join(lines)


def format_left_out(left_out: list) -> list[str]:
    if not left_out:
        return []
    lines = ["Not asked:"]
    for topic, why in left_out:
        lines += wrap(f"{topic}: {why}", "  - ", "    ")
    return lines


def format_readme_complete(path, left_out: list) -> str:
    """Why no AI call is needed for the README."""
    lines = [
        f"{printable(str(path)) if path else 'The README'} needs no section DevAI "
        "can ask for. Nothing was sent."
    ]
    return "\n".join(lines + format_left_out(left_out))


def format_readme_proposal(result: AIResult, plan, applying: bool = False) -> str:
    """Render the README change as a diff. Model output: untrusted."""
    lines = [f"PROPOSED README SECTIONS ({printable(result.model)})", SEPARATOR]
    change = plan.change
    if change is not None:
        # The diff keeps its own lines; only control characters are removed.
        lines += [printable(line) for line in change.diff.rstrip("\n").split("\n")]
        added = ", ".join(f"{heading} ({topic})" for topic, heading in plan.added)
        lines += [""]
        lines += wrap(f"Added:  {added}", "", "        ")
    else:
        lines.append("No usable section in the answer: nothing to add.")
    if plan.dropped:
        lines += ["", f"Not used ({len(plan.dropped)}):"]
        lines += [
            line
            for what, why in plan.dropped
            for line in wrap(f"{what}: {why}", "  - ", "    ")
        ]
    if plan.links:
        lines += ["", "Links the AI wrote (check them before applying):"]
        lines += [f"  - {printable(link)}" for link in plan.links]
    if change is not None:
        lines.append("")
        if plan.creates:
            lines += [
                "A new README.md: checked. devai docs finds each section in it, and",
                "every npm command in it runs a script that exists.",
            ]
        else:
            lines += [
                "Only additions: checked. Every line of the README is still there,",
                "unchanged and in order, and devai docs finds each new section with",
                "no new npm command that fails.",
            ]

    notes = result.report.notes
    if notes:
        lines += ["", "Notes from the AI:"]
        lines += [line for note in notes for line in wrap(note, "  - ", "    ")]

    usage = result.usage
    lines.append("")
    if change is None:
        lines.append("Nothing was changed.")
    elif not applying:
        action = "create it" if plan.creates else "write these sections"
        lines.append(f"Nothing was changed. To {action}, run again with --apply.")
    lines += [
        f"Tokens: {usage.input_tokens:,} in / {usage.output_tokens:,} out",
        "Written by AI. Read it before applying: instructions can be wrong.",
    ]
    return "\n".join(lines)
