"""Command-line interface. Parses arguments, calls the core, prints results."""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from devai import __version__
from devai.ai import build_context, estimate_tokens, serialize_context
from devai.ai.result import AIError, AIRequest, AIResult, LLMClient
from devai.ai.settings import PROVIDERS, AISettings, SettingsError, load_settings
from devai.analyzer import analyze_project
from devai.analyzer.files import list_project_files
from devai.chat import ChatError, Selection, build_chat_context, select_files
from devai.chat.retrieval import extra_file
from devai.checks import run_checks
from devai.fix.context import MAX_FIX_FILES, build_fix_context
from devai.json_report import chat_to_json, fix_to_json, review_to_json, to_json
from devai.models import CheckReport, Finding, ProjectInfo, Severity
from devai.report import (
    SEPARATOR,
    format_ai_review_section,
    format_ai_section,
    format_chat_answer,
    format_chat_header,
    format_fix_header,
    format_fix_proposal,
    format_report,
    format_review,
    plural,
    printable,
)
from devai.review import (
    Changes,
    ReviewError,
    collect_changes,
    review_report,
    run_review_checks,
)
from devai.review.context import build_review_context

# Same convention as linters such as ruff and eslint (D022).
EXIT_OK = 0
EXIT_FINDINGS = 1  # findings at or above the --fail-on level
EXIT_USAGE = 2  # no command, bad path or invalid argument (argparse uses 2 too)
EXIT_AI_ERROR = 3  # the AI step failed; the deterministic report was still printed

FAIL_ON_LEVELS = ["high", "medium", "low", "none"]

# Shown on stderr while the model works, per AI task.
PROGRESS = {
    "fix": "Asking {model} for a fix…",
    "analysis": "Analyzing with {model}…",
    "review": "Reviewing with {model}…",
    "chat": "Asking {model}…",
}
LOCAL_PROGRESS = {
    "fix": "Asking {model} for a fix locally (nothing leaves this machine)…",
    "analysis": "Analyzing locally with {model} (nothing leaves this machine)…",
    "review": "Reviewing locally with {model} (nothing leaves this machine)…",
    "chat": "Asking {model} locally (nothing leaves this machine)…",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="devai",
        description="AI-powered developer assistant for code analysis.",
    )
    parser.add_argument("--version", action="version", version=f"devai {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    analyze = subparsers.add_parser("analyze", help="analyze a project directory")
    analyze.add_argument(
        "path",
        nargs="?",
        default=".",
        help="project directory to analyze (default: current directory)",
    )
    add_output_options(analyze)
    analyze.add_argument(
        "--ai",
        action="store_true",
        help="add a free AI analysis (OpenCode free models or local Ollama): "
        "uses a project summary, never code, and asks before sending (see README)",
    )
    analyze.add_argument(
        "--dry-run",
        action="store_true",
        help="with --ai: show exactly what would be sent, without sending it",
    )
    add_ai_send_options(analyze)

    review = subparsers.add_parser(
        "review", help="check the current git changes before committing"
    )
    review.add_argument(
        "path",
        nargs="?",
        default=".",
        help="directory inside a git repository (default: current directory)",
    )
    which = review.add_mutually_exclusive_group()
    which.add_argument(
        "--staged",
        action="store_true",
        help="only staged changes: what the next commit would contain",
    )
    which.add_argument(
        "--base",
        metavar="REF",
        help="committed changes since the branch left REF, like a pull request",
    )
    add_output_options(review)
    review.add_argument(
        "--ai",
        action="store_true",
        help="add a free AI review of the changed code (asks before sending; see "
        "README)",
    )
    review.add_argument(
        "--dry-run",
        action="store_true",
        help="with --ai: show exactly what code would be sent, without sending it",
    )
    add_ai_send_options(review)

    chat = subparsers.add_parser(
        "chat", help="ask a free AI about a project, with files you approve"
    )
    chat.add_argument(
        "path",
        nargs="?",
        default=".",
        help="project directory (default: current directory)",
    )
    chat.add_argument(
        "--ask",
        metavar="QUESTION",
        help="ask one question and exit (without it: an interactive chat)",
    )
    chat.add_argument(
        "--file",
        action="append",
        default=[],
        metavar="PATH",
        help="also send this project file (relative to the project); repeatable",
    )
    chat.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="output format (default: text)",
    )
    chat.add_argument(
        "--dry-run",
        action="store_true",
        help="show exactly what would be sent, without sending it",
    )
    add_ai_send_options(chat)

    fix = subparsers.add_parser(
        "fix",
        help="ask a free AI to propose a fix, shown as a diff (nothing is written)",
    )
    fix.add_argument(
        "path",
        nargs="?",
        default=".",
        help="project directory (default: current directory)",
    )
    fix.add_argument(
        "--file",
        action="append",
        default=[],
        required=True,
        metavar="PATH",
        help="a file the fix may change (1 to 3; repeat the option)",
    )
    fix.add_argument(
        "--ask", required=True, metavar="REQUEST", help="what to fix or change"
    )
    fix.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="output format (default: text)",
    )
    fix.add_argument(
        "--dry-run",
        action="store_true",
        help="show exactly what would be sent, without sending it",
    )
    add_ai_send_options(fix)

    return parser


def add_ai_send_options(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="with --ai: send without asking (required when not in a terminal)",
    )
    command.add_argument(
        "--provider",
        choices=PROVIDERS,
        help="with --ai: opencode (default, free models via your OpenCode CLI) or "
        "ollama (local model); overrides DEVAI_AI_PROVIDER",
    )


def add_output_options(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="output format (default: text)",
    )
    command.add_argument(
        "--fail-on",
        choices=FAIL_ON_LEVELS,
        default="none",
        metavar="LEVEL",
        help="exit with code 1 if there is a finding of this severity or higher: "
        "high, medium, low or none (default: none)",
    )


class SetupError(Exception):
    """AI analysis can't start (missing extra, no terminal to confirm...)."""


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return an exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "chat":
        return run_chat(args)
    if args.command == "fix":
        return run_fix(args)
    if args.command not in ("analyze", "review"):
        parser.print_help()
        return EXIT_USAGE
    for option in ("dry_run", "yes", "provider"):
        if getattr(args, option) and not args.ai:
            flag = "--" + option.replace("_", "-")
            parser.error(f"{flag} requires --ai")  # exits with code 2
    return run_review(args) if args.command == "review" else run_analyze(args)


def run_analyze(args: argparse.Namespace) -> int:
    path = Path(args.path)
    try:
        info = analyze_project(path)
    except NotADirectoryError:
        print_error(f"not a directory: {path}")
        return EXIT_USAGE

    checks = run_checks(info)
    if args.ai and args.dry_run:
        print(format_ai_preview(info, checks, args.format))
        return EXIT_OK  # inspecting the context never fails the run

    ai: tuple[LLMClient, AISettings] | None = None
    if args.ai:
        try:
            ai = prepare_ai(assume_yes=args.yes, provider=args.provider)
        except (SettingsError, SetupError) as problem:
            print_error(str(problem))
            return EXIT_USAGE  # nothing was analyzed or sent yet

    ai_result, ai_failed = None, False
    if args.format == "json":
        if ai:
            ai_result, ai_failed = analyze_with_ai(
                *ai, build_context(info, checks), args.yes
            )
        print(to_json(info, checks, ai_result))
    else:
        # Show the report first: the user sees what is summarized before deciding.
        # flush: when stdout is a pipe, it must still come out before the question.
        print(format_report(info, checks), flush=True)
        if ai:
            ai_result, ai_failed = analyze_with_ai(
                *ai, build_context(info, checks), args.yes
            )
        if ai_result:
            print()
            print(format_ai_section(ai_result))

    if ai_failed:
        return EXIT_AI_ERROR
    # The AI's opinion never affects --fail-on: CI must be deterministic (D028).
    return EXIT_FINDINGS if should_fail(checks.findings, args.fail_on) else EXIT_OK


def run_review(args: argparse.Namespace) -> int:
    path = Path(args.path)
    try:
        changes = collect_changes(path, staged=args.staged, base=args.base)
    except NotADirectoryError:
        print_error(f"not a directory: {path}")
        return EXIT_USAGE
    except ReviewError as problem:
        print_error(str(problem))
        return EXIT_USAGE

    checks = run_review_checks(changes)
    if args.ai and args.dry_run:
        print(format_review_ai_preview(changes, checks, args.format))
        return EXIT_OK  # inspecting the context never fails the run

    ai: tuple[LLMClient, AISettings] | None = None
    if args.ai:
        try:
            ai = prepare_ai(assume_yes=args.yes, provider=args.provider)
        except (SettingsError, SetupError) as problem:
            print_error(str(problem))
            return EXIT_USAGE  # nothing was sent yet

    report = review_report(changes, checks)
    ai_result, discarded, ai_failed = None, 0, False
    if args.format == "json":
        if ai:
            ai_result, discarded, ai_failed = review_with_ai(
                *ai, changes, checks, args.yes
            )
        print(review_to_json(report, ai_result, discarded))
    else:
        # The local review first: the user sees the changes before deciding.
        # flush: when stdout is a pipe, it must still come out before the question.
        print(format_review(report), flush=True)
        if ai:
            ai_result, discarded, ai_failed = review_with_ai(
                *ai, changes, checks, args.yes
            )
        if ai_result:
            print()
            print(format_ai_review_section(ai_result, discarded))

    if ai_failed:
        return EXIT_AI_ERROR
    # The AI's opinion never affects --fail-on (D028).
    return (
        EXIT_FINDINGS if should_fail(report.checks.findings, args.fail_on) else EXIT_OK
    )


def run_chat(args: argparse.Namespace) -> int:
    if not args.ask:
        if args.dry_run:
            print_error('--dry-run needs a question: devai chat --ask "..." --dry-run')
            return EXIT_USAGE
        if not is_interactive():
            print_error('the interactive chat needs a terminal; use --ask "..."')
            return EXIT_USAGE
        return run_chat_session(args)

    path = Path(args.path)
    try:
        info = analyze_project(path)
    except NotADirectoryError:
        print_error(f"not a directory: {path}")
        return EXIT_USAGE
    try:
        selection = select_files(info.path, args.ask, tuple(args.file))
    except ChatError as problem:
        print_error(str(problem))
        return EXIT_USAGE

    checks = run_checks(info)
    context = build_chat_context(args.ask, info, checks, selection)
    if args.dry_run:
        print(format_chat_preview(context, selection, args.format))
        return EXIT_OK

    try:
        client, settings = prepare_ai(assume_yes=args.yes, provider=args.provider)
    except (SettingsError, SetupError) as problem:
        print_error(str(problem))
        return EXIT_USAGE

    if args.format == "text":
        # The files first: the user sees what would be sent before deciding.
        print(format_chat_header(info.name, context), flush=True)
    result, dropped, failed = ask_ai(client, settings, context, info.path, args.yes)
    if args.format == "json":
        print(chat_to_json(info.name, context, result, *dropped))
    elif result:
        print()
        print(format_chat_answer(result, *dropped))
    return EXIT_AI_ERROR if failed else EXIT_OK


def run_chat_session(args: argparse.Namespace) -> int:
    path = Path(args.path)
    try:
        info = analyze_project(path)
    except NotADirectoryError:
        print_error(f"not a directory: {path}")
        return EXIT_USAGE
    try:
        client, settings = prepare_ai(assume_yes=args.yes, provider=args.provider)
        from devai.chat.session import ChatSession  # needs the [ai] extra
    except (SettingsError, SetupError) as problem:
        print_error(str(problem))
        return EXIT_USAGE

    session = ChatSession(
        info, run_checks(info), client, settings, read_line, print, args.yes
    )
    for name in args.file:  # --file pins files for the whole conversation
        session.pin(name)
    session.run()
    return EXIT_OK


def read_line(prompt: str) -> str | None:
    """One line typed in the terminal; None when the user leaves (Ctrl+D, Ctrl+C)."""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def ask_ai(
    client: LLMClient,
    settings: AISettings,
    context: dict,
    root: Path,
    assume_yes: bool,
) -> tuple[AIResult | None, tuple[int, int], bool]:
    """Returns (grounded result, (sources dropped, suggestions dropped), failed)."""
    from devai.chat.ai import (  # needs the [ai] extra
        chat_question,
        chat_request,
        ground_answer,
    )

    result, failed = run_ai(
        client,
        settings,
        chat_request(context),
        chat_question(context, settings),
        assume_yes,
        task="chat",
    )
    if result is None:
        return None, (0, 0), failed
    answer, dropped_sources, dropped_suggestions = ground_answer(
        result.report, context, root
    )
    return replace(result, report=answer), (dropped_sources, dropped_suggestions), False


def run_fix(args: argparse.Namespace) -> int:
    """Propose a fix and show it as a diff. Never writes to the project (D043)."""
    if len(args.file) > MAX_FIX_FILES:
        print_error(f"a fix may change at most {MAX_FIX_FILES} files (--file)")
        return EXIT_USAGE
    path = Path(args.path)
    try:
        info = analyze_project(path)
    except NotADirectoryError:
        print_error(f"not a directory: {path}")
        return EXIT_USAGE
    allowed = list_project_files(info.path).files
    try:
        files = [
            extra_file(info.path, name, allowed, "named with --file")
            for name in args.file
        ]
    except ChatError as problem:
        print_error(str(problem))
        return EXIT_USAGE

    context = build_fix_context(args.ask, info, run_checks(info), files)
    if args.dry_run:
        print(format_fix_preview(context, args.format))
        return EXIT_OK

    try:
        client, settings = prepare_ai(assume_yes=args.yes, provider=args.provider)
        from devai.fix.ai import fix_question, fix_request  # needs the [ai] extra
        from devai.fix.edits import FixError, apply_edits
    except (SettingsError, SetupError) as problem:
        print_error(str(problem))
        return EXIT_USAGE

    if args.format == "text":
        print(format_fix_header(info.name, context), flush=True)
    result, failed = run_ai(
        client,
        settings,
        fix_request(context),
        fix_question(context, settings),
        args.yes,
        task="fix",
    )
    changes, rejected = [], None
    if result is not None:
        try:
            changes = apply_edits(result.report, {f.path: f.text for f in files})
        except FixError as problem:
            rejected = str(problem)
            print_error(
                f"The proposed fix was rejected: {rejected}. Nothing was changed."
            )

    if args.format == "json":
        print(fix_to_json(info.name, context, result, changes, rejected))
    elif result is not None and rejected is None:
        print()
        print(format_fix_proposal(result, changes))
    return EXIT_AI_ERROR if failed or rejected else EXIT_OK


def prepare_ai(assume_yes: bool, provider: str | None) -> tuple[LLMClient, AISettings]:
    settings = load_settings(provider=provider)
    if settings.leaves_machine and not assume_yes and not is_interactive():
        raise SetupError(
            f"--ai needs your confirmation before sending data to "
            f"{settings.destination}. Run it in a terminal, or add --yes to confirm."
        )
    return create_ai_client(settings), settings


def create_ai_client(settings: AISettings) -> LLMClient:
    # Imported here: AI support is an optional extra (it needs Pydantic).
    try:
        if settings.provider == "ollama":
            from devai.ai.ollama_client import OllamaClient

            return OllamaClient(settings)
        from devai.ai.opencode_client import OpenCodeClient

        return OpenCodeClient(settings)
    except ImportError as error:
        raise SetupError(
            "AI support is not installed. Install it with: pip install 'devai[ai]'"
        ) from error


def run_ai(
    client: LLMClient,
    settings: AISettings,
    request: AIRequest,
    question: str,
    assume_yes: bool,
    task: str = "analysis",
) -> tuple[AIResult | None, bool]:
    """Ask `question` if data leaves the machine, then send `request`.

    Returns (result, failed).
    """
    if settings.leaves_machine:
        if not assume_yes and not confirm_sending(settings, question):
            print(f"devai: AI {task} skipped. Nothing was sent.", file=sys.stderr)
            return None, False
        progress = PROGRESS[task].format(model=settings.model)
    else:
        progress = LOCAL_PROGRESS[task].format(model=settings.model)

    print(progress, file=sys.stderr, flush=True)
    try:
        return client.complete(request), False
    except AIError as problem:
        print_error(f"AI {task} failed: {problem}")
        return None, True


def analyze_with_ai(
    client: LLMClient, settings: AISettings, context: dict, assume_yes: bool
) -> tuple[AIResult | None, bool]:
    from devai.ai.analysis import analysis_request  # needs the [ai] extra

    tokens = estimate_tokens(serialize_context(context))
    question = (
        f"Send a project summary (~{tokens:,} tokens, no source code) to "
        f"{settings.destination}?"
    )
    return run_ai(client, settings, analysis_request(context), question, assume_yes)


def review_with_ai(
    client: LLMClient,
    settings: AISettings,
    changes: Changes,
    checks: CheckReport,
    assume_yes: bool,
) -> tuple[AIResult | None, int, bool]:
    """Returns (result with grounded issues, issues discarded, failed)."""
    from devai.review.ai import (  # needs the [ai] extra
        ground_issues,
        review_question,
        review_request,
    )

    context = build_review_context(changes, checks)
    if not context["diffs"]:
        print("devai: AI review skipped: no code can be sent.", file=sys.stderr)
        return None, 0, False

    result, failed = run_ai(
        client,
        settings,
        review_request(context),
        review_question(context, settings),
        assume_yes,
        task="review",
    )
    if result is None:
        return None, 0, failed
    report, discarded = ground_issues(result.report, context)
    return replace(result, report=report), discarded, False


def is_interactive() -> bool:
    return sys.stdin.isatty()


def confirm_sending(settings: AISettings, question: str) -> bool:
    """Ask on stderr, so stdout stays clean for the report or JSON."""
    if settings.data_note:
        print(f"Note: {settings.data_note}.", file=sys.stderr)
    print(
        f"{question} Preview it with --dry-run. [y/N] ",
        end="",
        file=sys.stderr,
        flush=True,
    )
    return sys.stdin.readline().strip().lower() in {"y", "yes"}


def print_error(message: str) -> None:
    print(f"devai: error: {message}", file=sys.stderr)


def should_fail(findings: tuple[Finding, ...], fail_on: str) -> bool:
    if fail_on == "none":
        return False
    threshold = Severity(fail_on)
    return any(finding.severity.rank >= threshold.rank for finding in findings)


def format_ai_preview(
    info: ProjectInfo, checks: CheckReport, output_format: str
) -> str:
    """Show the AI context exactly as it would be sent. Makes no network call."""
    context = build_context(info, checks)
    if output_format == "json":
        return json.dumps(context, indent=2, ensure_ascii=False)

    compact = serialize_context(context)
    return "\n".join(
        [
            "AI CONTEXT PREVIEW (dry run: nothing was sent)",
            SEPARATOR,
            json.dumps(context, indent=2, ensure_ascii=False),
            SEPARATOR,
            f"Size when sent: {len(compact):,} characters "
            f"(~{estimate_tokens(compact):,} tokens, estimated)",
        ]
    )


def format_review_ai_preview(
    changes: Changes, checks: CheckReport, output_format: str
) -> str:
    """Show the code an AI review would receive, exactly. Makes no network call."""
    context = build_review_context(changes, checks)
    if output_format == "json":
        return json.dumps(context, indent=2, ensure_ascii=False)

    compact = serialize_context(context)
    included = {diff["path"]: len(diff["lines"]) for diff in context["diffs"]}
    not_sent = [
        (file["path"], file["diff"])
        for file in context["files"]
        if file["diff"] not in ("included", "no changed lines")
    ]
    lines = ["AI REVIEW CONTEXT PREVIEW (dry run: nothing was sent)", SEPARATOR]
    if included:
        width = max(len(printable(path)) for path in included)
        lines.append("Code from these files would be sent (changed hunks only):")
        lines += [
            f"  {printable(path):<{width}}  {count} lines"
            for path, count in included.items()
        ]
    else:
        lines.append("No code would be sent.")
    if not_sent:
        width = max(len(printable(path)) for path, _ in not_sent)
        lines.append("Not sent:")
        lines += [f"  {printable(path):<{width}}  {why}" for path, why in not_sent]
    lines += [
        SEPARATOR,
        json.dumps(context, indent=2, ensure_ascii=False),
        SEPARATOR,
        f"Size when sent: {len(compact):,} characters "
        f"(~{estimate_tokens(compact):,} tokens, estimated), "
        f"{context['redacted_lines']} lines redacted",
    ]
    return "\n".join(lines)


def format_chat_preview(context: dict, selection: Selection, output_format: str) -> str:
    """Show what a chat question would send, exactly. Makes no network call."""
    if output_format == "json":
        return json.dumps(context, indent=2, ensure_ascii=False)

    compact = serialize_context(context)
    terms = ", ".join(selection.terms) or "none"
    lines = [
        "AI CHAT CONTEXT PREVIEW (dry run: nothing was sent)",
        SEPARATOR,
        f"Question:     {printable(context['question'])}",
        f"Search terms: {printable(terms)}",
    ]
    if context["files"]:
        width = max(len(printable(file["path"])) for file in context["files"])
        lines.append("Files that would be sent:")
        lines += [
            f"  {printable(file['path']):<{width}}  {printable(file['reason'])}"
            f"  ({len(file['lines'])} {plural(len(file['lines']), 'line')})"
            for file in context["files"]
        ]
    else:
        lines.append(
            "No relevant files found: only the project summary would be sent. "
            "Add files with --file."
        )
    lines += [
        SEPARATOR,
        json.dumps(context, indent=2, ensure_ascii=False),
        SEPARATOR,
        f"Size when sent: {len(compact):,} characters "
        f"(~{estimate_tokens(compact):,} tokens, estimated), "
        f"{context['redacted_lines']} lines redacted",
    ]
    return "\n".join(lines)


def format_fix_preview(context: dict, output_format: str) -> str:
    """Show what a fix request would send, exactly. Makes no network call."""
    if output_format == "json":
        return json.dumps(context, indent=2, ensure_ascii=False)
    compact = serialize_context(context)
    lines = [
        "AI FIX CONTEXT PREVIEW (dry run: nothing was sent, nothing was changed)",
        SEPARATOR,
        f"Request: {printable(context['request'])}",
        "Files that would be sent in full:",
        *(f"  {printable(file['path'])}" for file in context["files"]),
        SEPARATOR,
        json.dumps(context, indent=2, ensure_ascii=False),
        SEPARATOR,
        f"Size when sent: {len(compact):,} characters "
        f"(~{estimate_tokens(compact):,} tokens, estimated), "
        f"{context['redacted_lines']} lines redacted",
    ]
    return "\n".join(lines)
