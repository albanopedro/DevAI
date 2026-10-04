"""Render analysis results as JSON for scripts and CI."""

import json
from dataclasses import asdict

from devai import __version__
from devai.ai.result import AIResult
from devai.models import CheckReport, ProjectInfo, ReviewReport

# Bump when the JSON structure changes in a backwards-incompatible way.
SCHEMA_VERSION = 1


def to_json(info: ProjectInfo, checks: CheckReport, ai: AIResult | None = None) -> str:
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "project": asdict(info),
        "checks": asdict(checks),
    }
    if ai is not None:  # an added key: still schema version 1 (D023)
        document["ai"] = {
            "model": ai.model,
            "usage": asdict(ai.usage),
            "report": ai.report.model_dump(mode="json"),
        }
    # default=str turns paths into strings; StrEnum values already are strings.
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


def review_to_json(
    report: ReviewReport, ai: AIResult | None = None, discarded: int = 0
) -> str:
    """`devai review` as JSON. Like the text report, it never contains code."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "review": asdict(report),
    }
    if ai is not None:  # an added key: still schema version 1 (D023)
        document["ai"] = {
            "model": ai.model,
            "usage": asdict(ai.usage),
            "report": ai.report.model_dump(mode="json"),
            "discarded_issues": discarded,
        }
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


def chat_to_json(
    name: str,
    context: dict,
    ai: AIResult | None,
    dropped_sources: int = 0,
    dropped_suggestions: int = 0,
) -> str:
    """A chat question as JSON: the files sent (names, reasons) and the answer."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "chat": {
            "project": name,
            "question": context["question"],
            "files": [
                {"path": file["path"], "reason": file["reason"]}
                for file in context["files"]
            ],
        },
    }
    if ai is not None:
        document["ai"] = {
            "model": ai.model,
            "usage": asdict(ai.usage),
            "answer": ai.report.model_dump(mode="json"),
            "dropped_sources": dropped_sources,
            "dropped_suggestions": dropped_suggestions,
        }
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


def fix_to_json(
    name: str,
    context: dict,
    ai: AIResult | None,
    changes: list,
    rejected: str | None,
) -> str:
    """A fix proposal as JSON: the files, the proposal, the diff (nothing applied)."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "fix": {
            "project": name,
            "request": context["request"],
            "files": [file["path"] for file in context["files"]],
            "applied": False,
        },
    }
    if ai is not None:
        document["ai"] = {
            "model": ai.model,
            "usage": asdict(ai.usage),
            "proposal": ai.report.model_dump(mode="json"),
            "rejected": rejected,
            "diffs": {str(change.path): change.diff for change in changes},
        }
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


def coverage_to_json(name: str, coverage) -> str:
    """`devai test` as JSON."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "test_map": {
            "project": name,
            "test_files": coverage.test_files,
            "frameworks": list(coverage.frameworks),
            "sources_checked": coverage.sources_checked,
            "languages": list(coverage.languages),
            "without_tests": [str(path) for path in coverage.without_tests],
            "untested_symbols": {
                str(path): list(symbols) for path, symbols in coverage.untested_symbols
            },
            "not_parsed": [str(path) for path in coverage.not_parsed],
            "estimate": True,  # names only, not a coverage measurement
        },
    }
    return json.dumps(document, indent=2, ensure_ascii=False)


def docs_to_json(name: str, docs) -> str:
    """`devai docs` as JSON."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "docs_map": {
            "project": name,
            "sources_checked": docs.sources_checked,
            "languages": list(docs.languages),
            "public_names": docs.public_names,
            "documented": docs.documented,
            "undocumented": {
                str(path): list(names) for path, names in docs.undocumented
            },
            "not_parsed": [str(path) for path in docs.not_parsed],
            "readme": None if docs.readme is None else asdict(docs.readme),
            "estimate": True,  # names and patterns; README scripts are exact
        },
    }
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


def generated_tests_to_json(
    name: str, context: dict, ai: AIResult | None, path, rejected: str | None
) -> str:
    """A test proposal as JSON (nothing created)."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "tests": {
            "project": name,
            "source": context["source"]["path"],
            "existing_tests": [test["path"] for test in context["existing_tests"]],
            "created": False,
        },
    }
    if ai is not None:
        document["ai"] = {
            "model": ai.model,
            "usage": asdict(ai.usage),
            "proposal": ai.report.model_dump(mode="json"),
            "path": str(path) if path else None,
            "rejected": rejected,
        }
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


def doc_proposal_to_json(
    name: str, context: dict, ai: AIResult | None, plan, rejected: str | None
) -> str:
    """A docs proposal as JSON: the names, the proposal, the diff (nothing applied)."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "docs": {
            "project": name,
            "file": context["file"]["path"],
            "names": context["names"],
            "applied": False,
        },
    }
    if ai is not None:
        change = plan.change if plan is not None else None
        document["ai"] = {
            "model": ai.model,
            "usage": asdict(ai.usage),
            "proposal": ai.report.model_dump(mode="json"),
            "rejected": rejected,
            "added": list(plan.added) if plan is not None else [],
            "dropped": [
                {"name": dropped, "reason": why}
                for dropped, why in (plan.dropped if plan is not None else ())
            ],
            "diff": change.diff if change is not None else None,
        }
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


def readme_proposal_to_json(
    name: str, context: dict, ai: AIResult | None, plan, rejected: str | None
) -> str:
    """README sections as JSON: the topics, the proposal, the diff (nothing applied)."""
    readme = context["readme"]
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "readme": {
            "project": name,
            "path": readme["path"],
            "exists": readme["exists"],
            "topics": context["topics"],
            "applied": False,
        },
    }
    if ai is not None:
        change = plan.change if plan is not None else None
        document["ai"] = {
            "model": ai.model,
            "usage": asdict(ai.usage),
            "proposal": ai.report.model_dump(mode="json"),
            "rejected": rejected,
            "added": [
                {"topic": topic, "heading": heading}
                for topic, heading in (plan.added if plan is not None else ())
            ],
            "dropped": [
                {"section": what, "reason": why}
                for what, why in (plan.dropped if plan is not None else ())
            ],
            "links": list(plan.links) if plan is not None else [],
            "creates": plan.creates if plan is not None else False,
            "diff": change.diff if change is not None else None,
        }
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


def pull_to_json(
    pull, report: ReviewReport, ai: AIResult | None = None, discarded: int = 0
) -> str:
    """`devai pr` as JSON: the review's JSON, plus the pull request's facts."""
    document = json.loads(review_to_json(report, ai, discarded))
    document["pull_request"] = asdict(pull)
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


def issue_to_json(issue, ai: AIResult | None = None, dropped: int = 0) -> str:
    """`devai issue` as JSON: the issue, and the AI's plan if one was made."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "issue": asdict(issue),
    }
    if ai is not None:
        document["ai"] = {
            "model": ai.model,
            "usage": asdict(ai.usage),
            "plan": ai.report.model_dump(mode="json"),
            "files_dropped": dropped,
        }
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


def github_list_to_json(kind: str, repo: str, items: list[dict]) -> str:
    """`devai pulls` / `devai issues` as JSON."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        kind: {"repo": repo, "open": items},
    }
    return json.dumps(document, indent=2, ensure_ascii=False)
