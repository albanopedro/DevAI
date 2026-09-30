"""Command-line interface. Parses arguments, calls the core, prints results."""

import argparse
import json
import sys
from pathlib import Path

from devai import __version__
from devai.ai import build_context, estimate_tokens, serialize_context
from devai.ai.result import AIError, AIResult, LLMClient
from devai.ai.settings import PROVIDERS, AISettings, SettingsError, load_settings
from devai.analyzer import analyze_project
from devai.checks import run_checks
from devai.json_report import to_json
from devai.models import CheckReport, Finding, ProjectInfo, Severity
from devai.report import SEPARATOR, format_ai_section, format_report

# Same convention as linters such as ruff and eslint (D022).
EXIT_OK = 0
EXIT_FINDINGS = 1  # findings at or above the --fail-on level
EXIT_USAGE = 2  # no command, bad path or invalid argument (argparse uses 2 too)
EXIT_AI_ERROR = 3  # the AI step failed; the deterministic report was still printed

FAIL_ON_LEVELS = ["high", "medium", "low", "none"]


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
    analyze.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="output format (default: text)",
    )
    analyze.add_argument(
        "--fail-on",
        choices=FAIL_ON_LEVELS,
        default="none",
        metavar="LEVEL",
        help="exit with code 1 if there is a finding of this severity or higher: "
        "high, medium, low or none (default: none)",
    )
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
    analyze.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="with --ai: send without asking (required when not in a terminal)",
    )
    analyze.add_argument(
        "--provider",
        choices=PROVIDERS,
        help="with --ai: opencode (default, free models via your OpenCode CLI) or "
        "ollama (local model); overrides DEVAI_AI_PROVIDER",
    )

    return parser


class SetupError(Exception):
    """AI analysis can't start (missing extra, no terminal to confirm...)."""


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return an exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "analyze":
        parser.print_help()
        return EXIT_USAGE
    if args.dry_run and not args.ai:
        parser.error("--dry-run requires --ai")  # exits with code 2
    if args.yes and not args.ai:
        parser.error("--yes requires --ai")
    if args.provider and not args.ai:
        parser.error("--provider requires --ai")
    return run_analyze(args)


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
            ai_result, ai_failed = run_ai(*ai, build_context(info, checks), args.yes)
        print(to_json(info, checks, ai_result))
    else:
        # Show the report first: the user sees what is summarized before deciding.
        print(format_report(info, checks))
        if ai:
            ai_result, ai_failed = run_ai(*ai, build_context(info, checks), args.yes)
        if ai_result:
            print()
            print(format_ai_section(ai_result))

    if ai_failed:
        return EXIT_AI_ERROR
    # The AI's opinion never affects --fail-on: CI must be deterministic (D028).
    return EXIT_FINDINGS if should_fail(checks.findings, args.fail_on) else EXIT_OK


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
    client: LLMClient, settings: AISettings, context: dict, assume_yes: bool
) -> tuple[AIResult | None, bool]:
    """Ask for consent if data leaves the machine, then call the model.

    Returns (result, failed).
    """
    tokens = estimate_tokens(serialize_context(context))
    if settings.leaves_machine:
        if not assume_yes and not confirm_sending(settings, tokens):
            print("devai: AI analysis skipped. Nothing was sent.", file=sys.stderr)
            return None, False
        progress = f"Analyzing with {settings.model}…"
    else:
        progress = (
            f"Analyzing locally with {settings.model} (nothing leaves this machine)…"
        )

    print(progress, file=sys.stderr, flush=True)
    try:
        return client.analyze(context), False
    except AIError as problem:
        print_error(f"AI analysis failed: {problem}")
        return None, True


def is_interactive() -> bool:
    return sys.stdin.isatty()


def confirm_sending(settings: AISettings, tokens: int) -> bool:
    """Ask on stderr, so stdout stays clean for the report or JSON."""
    if settings.data_note:
        print(f"Note: {settings.data_note}.", file=sys.stderr)
    print(
        f"Send a project summary (~{tokens:,} tokens, no source code) to "
        f"{settings.destination}? Preview it with --dry-run. [y/N] ",
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
