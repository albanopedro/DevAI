import socket
from types import SimpleNamespace

import anthropic
import httpx2
import pydantic
import pytest
from conftest import fake_ai_report

from devai.ai.client import FALLBACK_BETA, MAX_OUTPUT_TOKENS, AnthropicClient
from devai.ai.context import serialize_context
from devai.ai.prompt import SYSTEM_PROMPT, build_user_message
from devai.ai.result import AIError, AIUsage
from devai.ai.schema import AIReport
from devai.ai.settings import AISettings

CONTEXT = {"context_version": 1, "project": {"name": "demo"}, "findings": []}
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


class FakeSDK:
    """Stands in for anthropic.Anthropic: records calls, never touches the network."""

    def __init__(self, response=None, error=None):
        self.calls = []
        self._response = response
        self._error = error
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


def response(**overrides):
    fields = dict(
        stop_reason="end_turn",
        stop_details=None,
        parsed_output=fake_ai_report(),
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=1200, output_tokens=2400),
    )
    return SimpleNamespace(**(fields | overrides))


DEFAULT_SETTINGS = AISettings()


def client_with(sdk, settings=DEFAULT_SETTINGS):
    return AnthropicClient(settings, sdk=sdk)


# --- the request -------------------------------------------------------------


def test_request_sends_only_the_serialized_context():
    sdk = FakeSDK(response())

    client_with(sdk, AISettings("claude-opus-5-5", "high")).analyze(CONTEXT)

    [call] = sdk.calls
    assert call["model"] == "claude-opus-5-5"
    assert call["system"] == SYSTEM_PROMPT
    assert call["messages"] == [
        {"role": "user", "content": build_user_message(serialize_context(CONTEXT))}
    ]
    assert call["output_format"] is AIReport
    assert call["output_config"] == {"effort": "high"}
    assert call["max_tokens"] == MAX_OUTPUT_TOKENS
    assert call["betas"] == [FALLBACK_BETA]
    assert call["fallbacks"] == "default"


def test_result_reports_the_model_that_answered_and_usage():
    sdk = FakeSDK(response(model="claude-fallback-model"))

    result = client_with(sdk).analyze(CONTEXT)

    assert result.report == fake_ai_report()
    assert result.model == "claude-fallback-model"
    assert result.usage == AIUsage(1200, 2400)


# --- responses that are not a usable report ----------------------------------


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "stop_reason": "refusal",
                "stop_details": SimpleNamespace(category="cyber"),
            },
            "declined to analyze this project (cyber)",
        ),
        ({"stop_reason": "refusal"}, "declined to analyze this project."),
        ({"stop_reason": "max_tokens"}, "cut off"),
        ({"parsed_output": None}, "no structured report"),
    ],
)
def test_unusable_responses_become_ai_errors(overrides, message):
    sdk = FakeSDK(response(**overrides))

    with pytest.raises(AIError, match=message.replace("(", r"\(").replace(")", r"\)")):
        client_with(sdk).analyze(CONTEXT)


# --- SDK errors become clear messages ----------------------------------------


def status_error(error_class, status):
    return error_class(
        "error", response=httpx2.Response(status, request=REQUEST), body=None
    )


def validation_error():
    try:
        AIReport.model_validate({"summary": "missing fields"})
    except pydantic.ValidationError as error:
        return error
    raise AssertionError("expected a validation error")


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (status_error(anthropic.AuthenticationError, 401), "rejected the API key"),
        (status_error(anthropic.PermissionDeniedError, 403), "no access to"),
        (status_error(anthropic.NotFoundError, 404), "was not found"),
        (status_error(anthropic.RateLimitError, 429), "rate limit"),
        (status_error(anthropic.BadRequestError, 400), "rejected the request"),
        (status_error(anthropic.InternalServerError, 500), "HTTP 500"),
        (anthropic.APITimeoutError(REQUEST), "timed out"),
        (anthropic.APIConnectionError(request=REQUEST), "Could not reach"),
        (validation_error(), "did not match the expected report format"),
        (
            TypeError('"Could not resolve authentication method. Expected one of..."'),
            "No Anthropic credentials found",
        ),
    ],
)
def test_sdk_errors_become_ai_errors(error, message):
    with pytest.raises(AIError, match=message):
        client_with(FakeSDK(error=error)).analyze(CONTEXT)


def test_unexpected_errors_are_not_hidden():
    with pytest.raises(TypeError, match="unrelated bug"):
        client_with(FakeSDK(error=TypeError("unrelated bug"))).analyze(CONTEXT)


def test_real_sdk_without_credentials_fails_clearly_and_offline(tmp_path, monkeypatch):
    for variable in ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"]:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # no `ant auth login` profile here
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))

    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", no_network)

    with pytest.raises(AIError, match="No Anthropic credentials found"):
        AnthropicClient(AISettings()).analyze(CONTEXT)
