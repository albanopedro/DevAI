"""The contract between an AI task (analysis, review) and a client (D037).

A task builds an AIRequest: the instructions, the message with its delimited
context, and the Pydantic model the answer must match. A client (OpenCode,
Ollama) only transports it and validates the answer against that model.

No third-party imports here, so report.py and json_report.py can use these
types even when the optional [ai] extra is not installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pydantic import BaseModel


class AIError(Exception):
    """The AI step failed. The message is safe to show to the user."""


@dataclass(frozen=True)
class AIRequest:
    system_prompt: str
    message: str  # the task's text with its delimited context; clients add the schema
    output: type[BaseModel]  # the answer must validate against this model
    title: str = "DevAI"  # shown where a client keeps history (OpenCode sessions)


@dataclass(frozen=True)
class AIUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class AIResult:
    report: Any  # an instance of the request's `output` model
    model: str
    usage: AIUsage


class LLMClient(Protocol):
    """Anything that can answer an AIRequest (OpenCode, Ollama...)."""

    def complete(self, request: AIRequest) -> AIResult: ...
