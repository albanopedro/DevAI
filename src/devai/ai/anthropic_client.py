"""Send the AI context to Claude and get a validated AIReport back.

This is the only module that talks to an external service. Each analysis is
one request: the fixed SYSTEM_PROMPT plus build_user_message(serialize_context(
context)), the same data `devai analyze --ai --dry-run` shows (D025, D027).
"""

from typing import Any

import anthropic
import pydantic

from devai.ai.context import serialize_context
from devai.ai.prompt import SYSTEM_PROMPT, build_user_message
from devai.ai.result import AIError, AIResult, AIUsage
from devai.ai.schema import AIReport
from devai.ai.settings import AISettings

MAX_OUTPUT_TOKENS = 16_000
TIMEOUT_SECONDS = 180.0
# If the model declines for policy reasons, the API retries on a
# server-chosen fallback model within the same request.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicClient:
    def __init__(self, settings: AISettings, sdk: anthropic.Anthropic | None = None):
        self.settings = settings
        # Credentials come from the environment (ANTHROPIC_API_KEY) or an
        # `ant auth login` profile; the SDK resolves them itself.
        self._sdk = sdk or anthropic.Anthropic(timeout=TIMEOUT_SECONDS)

    def analyze(self, context: dict[str, Any]) -> AIResult:
        try:
            response = self._sdk.beta.messages.parse(
                model=self.settings.model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": build_user_message(serialize_context(context)),
                    }
                ],
                output_format=AIReport,
                output_config={"effort": self.settings.effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except Exception as error:
            raise AIError(self.explain(error)) from error
        return to_result(response)

    def explain(self, error: Exception) -> str:
        """A user-facing message for a failed request; unknown errors re-raise."""
        model = self.settings.model
        # Most specific first: several of these are subclasses of the later ones.
        if isinstance(error, anthropic.AuthenticationError):
            return "Anthropic rejected the API key. Check ANTHROPIC_API_KEY."
        if isinstance(error, anthropic.PermissionDeniedError):
            return f"This API key has no access to {model}."
        if isinstance(error, anthropic.NotFoundError):
            return f"Model {model!r} was not found. Check DEVAI_AI_MODEL."
        if isinstance(error, anthropic.RateLimitError):
            return "Anthropic rate limit reached. Try again in a minute."
        if isinstance(error, anthropic.BadRequestError):
            return f"Anthropic rejected the request: {error.message}"
        if isinstance(error, anthropic.APIStatusError):
            return f"Anthropic API error (HTTP {error.status_code}). Try again later."
        if isinstance(error, anthropic.APITimeoutError):
            return "The request to Anthropic timed out."
        if isinstance(error, anthropic.APIConnectionError):
            return "Could not reach the Anthropic API. Check your connection."
        if isinstance(error, pydantic.ValidationError):
            return "The model's answer did not match the expected report format."
        # With no credentials at all, the SDK raises a plain TypeError before
        # any network access. Match it narrowly: other TypeErrors are bugs.
        if isinstance(error, TypeError) and "authentication method" in str(error):
            return "No Anthropic credentials found. Set ANTHROPIC_API_KEY."
        raise error


def to_result(response: Any) -> AIResult:
    if response.stop_reason == "refusal":
        category = getattr(response.stop_details, "category", None)
        reason = f" ({category})" if category else ""
        raise AIError(f"The model declined to analyze this project{reason}.")
    if response.stop_reason == "max_tokens":
        raise AIError("The model's answer was cut off before it finished.")
    if response.parsed_output is None:
        raise AIError("The model returned no structured report.")

    return AIResult(
        report=response.parsed_output,
        model=response.model,
        usage=AIUsage(response.usage.input_tokens, response.usage.output_tokens),
    )
