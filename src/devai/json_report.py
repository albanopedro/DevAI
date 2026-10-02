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
