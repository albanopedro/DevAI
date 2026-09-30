"""What an AI analysis returns, and how it fails.

No third-party imports here, so report.py and json_report.py can use these
types even when the optional [ai] extra is not installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from devai.ai.schema import AIReport


class AIError(Exception):
    """The AI step failed. The message is safe to show to the user."""


@dataclass(frozen=True)
class AIUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class AIResult:
    report: AIReport
    model: str  # the model that actually answered: may be a fallback model
    usage: AIUsage


class LLMClient(Protocol):
    """Anything that can turn an AI context into an AIResult (Anthropic, Ollama...)."""

    def analyze(self, context: dict[str, Any]) -> AIResult: ...
