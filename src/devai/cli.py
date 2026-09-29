"""Command-line interface. Parses arguments, calls the core, prints results."""

import argparse
import sys
from pathlib import Path

from devai import __version__
from devai.models import ProjectInfo
from devai.scanner import scan_project

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_BAD_PATH = 2


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

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return an exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "analyze":
        return run_analyze(Path(args.path))

    parser.print_help()
    return EXIT_USAGE


def run_analyze(path: Path) -> int:
    try:
        info = scan_project(path)
    except NotADirectoryError:
        print(f"devai: error: not a directory: {path}", file=sys.stderr)
        return EXIT_BAD_PATH

    print(format_project_info(info))
    return EXIT_OK


def format_project_info(info: ProjectInfo) -> str:
    return "\n".join(
        [
            "DEVAI ANALYSIS",
            "─" * 36,
            f"Project:        {info.name}",
            f"Path:           {info.path}",
            f"Files:          {info.file_count}",
            f"Git repository: {yes_no(info.has_git)}",
            f"README:         {yes_no(info.has_readme)}",
        ]
    )


def yes_no(value: bool) -> str:
    return "yes" if value else "no"
