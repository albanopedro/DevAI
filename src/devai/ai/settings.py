"""AI settings, read from environment variables only.

DevAI never loads .env files (D026): it runs inside the project it analyzes,
so reading ./.env would mean reading that project's secrets.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


class SettingsError(ValueError):
    """An AI setting has an invalid value; the message is safe to show."""


@dataclass(frozen=True)
class AISettings:
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT


def load_settings(environ: Mapping[str, str] = os.environ) -> AISettings:
    model = environ.get("DEVAI_AI_MODEL", "").strip() or DEFAULT_MODEL
    effort = environ.get("DEVAI_AI_EFFORT", "").strip().lower() or DEFAULT_EFFORT
    if effort not in EFFORT_LEVELS:
        levels = ", ".join(EFFORT_LEVELS)
        raise SettingsError(f"DEVAI_AI_EFFORT must be one of {levels} (got {effort!r})")
    return AISettings(model=model, effort=effort)
