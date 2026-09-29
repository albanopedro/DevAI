"""Render a ProjectInfo as human-readable terminal text."""

from devai.models import Manifest, ProjectInfo, TestSummary

SEPARATOR = "─" * 36


def format_project_info(info: ProjectInfo) -> str:
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
