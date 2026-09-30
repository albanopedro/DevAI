"""Build the data package an AI model may receive about a project.

This module is the privacy boundary between DevAI and any external AI
service (D025). Rules:

- Allow-list: every field is picked explicitly. A new field on ProjectInfo
  or CheckReport never reaches the AI unless it is added here on purpose.
- Summaries only: no file contents, no full file list, no absolute paths,
  no dependency versions. Secrets appear only as the masked evidence the
  report already shows ("AKIA…").
- Bounded size: long lists are cut, and the cut is recorded in "truncated"
  so the model knows the data is incomplete.

Strings in the context (file names, dependency names) come from the
analyzed project and are untrusted data, never instructions.
"""

import json
from collections.abc import Sequence
from typing import Any, TypeVar

from devai.models import CheckReport, Finding, Manifest, ProjectInfo

# Bump when the structure of the context changes.
CONTEXT_VERSION = 1

MAX_FINDINGS = 50
MAX_MANIFESTS = 20
MAX_DEPENDENCIES_PER_MANIFEST = 100
MAX_CONFIG_FILES = 30
MAX_DIRECTORIES = 30

T = TypeVar("T")
Truncated = dict[str, dict[str, int]]  # section → {"shown": n, "total": m}


def build_context(info: ProjectInfo, checks: CheckReport) -> dict[str, Any]:
    """Return the JSON-serializable context an AI model may receive."""
    truncated: Truncated = {}
    return {
        "context_version": CONTEXT_VERSION,
        "project": {
            "name": info.name,  # the directory name only, never the path
            "file_count": info.file_count,
            "has_git": info.has_git,
            "has_readme": info.has_readme,
        },
        "languages": [
            {"name": language.name, "files": language.files}
            for language in info.languages
        ],
        "frameworks": list(info.frameworks),
        "dependencies": [
            manifest_context(manifest, truncated)
            for manifest in cap(info.manifests, MAX_MANIFESTS, "manifests", truncated)
        ],
        "tests": {
            "files": info.tests.files,
            "frameworks": list(info.tests.frameworks),
        },
        "config_files": [
            str(path)
            for path in cap(
                info.config_files, MAX_CONFIG_FILES, "config_files", truncated
            )
        ],
        "structure": {
            "directories": [
                {"name": directory.name, "files": directory.files}
                for directory in cap(
                    info.directories, MAX_DIRECTORIES, "directories", truncated
                )
            ],
            "root_files": info.root_file_count,
        },
        "findings": [
            finding_context(finding)
            for finding in cap(checks.findings, MAX_FINDINGS, "findings", truncated)
        ],
        "passed_checks": list(checks.passed),
        "secret_scan": {
            "files_scanned": checks.secret_scan.scanned,
            "files_skipped": checks.secret_scan.skipped,
        },
        "truncated": truncated,
    }


def manifest_context(manifest: Manifest, truncated: Truncated) -> dict[str, Any]:
    dependencies = cap(
        manifest.dependencies,
        MAX_DEPENDENCIES_PER_MANIFEST,
        f"dependencies:{manifest.path}",
        truncated,
    )
    return {
        "manifest": str(manifest.path),
        "ecosystem": str(manifest.ecosystem),
        "parsed": manifest.parsed,
        # Names only: versions add tokens without helping the analysis.
        "runtime": [
            dependency.name for dependency in dependencies if not dependency.dev
        ],
        "dev": [dependency.name for dependency in dependencies if dependency.dev],
    }


def finding_context(finding: Finding) -> dict[str, Any]:
    return {
        "rule_id": finding.rule_id,
        "severity": str(finding.severity),
        "message": finding.message,
        "file": str(finding.file) if finding.file else None,
        "line": finding.line,
        "evidence": finding.evidence,  # already masked by the checks (D021)
    }


def cap(
    items: Sequence[T], limit: int, section: str, truncated: Truncated
) -> Sequence[T]:
    """Return at most `limit` items, recording in `truncated` if any were cut."""
    if len(items) > limit:
        truncated[section] = {"shown": limit, "total": len(items)}
    return items[:limit]


def serialize_context(context: dict[str, Any]) -> str:
    """Compact JSON: the exact form sent to the model (fewer tokens than indented).

    "<" is escaped as \\u003c (still valid, equivalent JSON), so a name from the
    project such as "</project_context>" can't close the prompt's delimiter.
    """
    text = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c")


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token). Exact counts need the API."""
    return -(-len(text) // 4)  # ceiling division
