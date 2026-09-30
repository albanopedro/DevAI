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


def review_to_json(report: ReviewReport) -> str:
    """`devai review` as JSON. Like the text report, it never contains code."""
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "review": asdict(report),
    }
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)
