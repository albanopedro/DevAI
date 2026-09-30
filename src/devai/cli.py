"""Command-line interface. Parses arguments, calls the core, prints results."""

import argparse
import json
import sys
from pathlib import Path

from devai import __version__
from devai.ai import build_context, estimate_tokens, serialize_context
from devai.analyzer import analyze_project
from devai.checks import run_checks
from devai.json_report import to_json
from devai.models import CheckReport, Finding, ProjectInfo, Severity
from devai.report import SEPARATOR, format_report

# Same convention as linters such as ruff and eslint (D022).
EXIT_OK = 0
EXIT_FINDINGS = 1  # findings at or above the --fail-on level
EXIT_USAGE = 2  # no command, bad path or invalid argument (argparse uses 2 too)

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
        help="add an AI analysis (sends a summary, never code; see README)",
    )
    analyze.add_argument(
        "--dry-run",
        action="store_true",
        help="with --ai: show exactly what would be sent, without sending it",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return an exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        if args.dry_run and not args.ai:
            parser.error("--dry-run requires --ai")  # exits with code 2
        if args.ai and not args.dry_run:
            print(
                "devai: error: AI analysis is not available yet (Phase 3b). "
                "Use --ai --dry-run to preview what would be sent.",
                file=sys.stderr,
            )
            return EXIT_USAGE
        return run_analyze(Path(args.path), args.format, args.fail_on, args.dry_run)

    parser.print_help()
    return EXIT_USAGE


def run_analyze(
    path: Path, output_format: str, fail_on: str, ai_dry_run: bool = False
) -> int:
    try:
        info = analyze_project(path)
    except NotADirectoryError:
        print(f"devai: error: not a directory: {path}", file=sys.stderr)
        return EXIT_USAGE

    checks = run_checks(info)
    if ai_dry_run:
        print(format_ai_preview(info, checks, output_format))
        return EXIT_OK  # inspecting the context never fails the run

    if output_format == "json":
        print(to_json(info, checks))
    else:
        print(format_report(info, checks))
    return EXIT_FINDINGS if should_fail(checks.findings, fail_on) else EXIT_OK


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
