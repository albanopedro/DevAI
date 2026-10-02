"""The analysis task: what `devai analyze --ai` asks the model (D025, D027)."""

from typing import Any

from devai.ai.context import serialize_context
from devai.ai.prompt import SYSTEM_PROMPT, build_user_message
from devai.ai.result import AIRequest
from devai.ai.schema import AIReport


def analysis_request(context: dict[str, Any]) -> AIRequest:
    return AIRequest(
        system_prompt=SYSTEM_PROMPT,
        message=build_user_message(serialize_context(context)),
        output=AIReport,
        title="DevAI analysis",
    )
