"""Render analysis results as JSON for scripts and CI."""

import json
from dataclasses import asdict

from devai import __version__
from devai.models import CheckReport, ProjectInfo

# Bump when the JSON structure changes in a backwards-incompatible way.
SCHEMA_VERSION = 1


def to_json(info: ProjectInfo, checks: CheckReport) -> str:
    document = {
        "schema_version": SCHEMA_VERSION,
        "devai_version": __version__,
        "project": asdict(info),
        "checks": asdict(checks),
    }
    # default=str turns paths into strings; StrEnum values already are strings.
    return json.dumps(document, indent=2, ensure_ascii=False, default=str)
