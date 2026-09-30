"""Run the AI analysis on a model served by Ollama, usually on this computer.

Same system prompt, same context (D025) and same AIReport as the Anthropic
client; only the transport differs. The API is one JSON POST, so this uses
urllib from the standard library instead of another dependency (D030).
"""

import json
import urllib.error
import urllib.request
from typing import Any

import pydantic

from devai.ai.context import serialize_context
from devai.ai.prompt import SYSTEM_PROMPT, build_user_message, schema_instructions
from devai.ai.result import AIError, AIResult, AIUsage
from devai.ai.schema import AIReport
from devai.ai.settings import AISettings

TIMEOUT_SECONDS = 300.0  # local models can be slow, especially on first load
# Ollama's default context window is small and truncates silently; the
# prompt, context and answer need room.
CONTEXT_WINDOW = 8192

# No proxy handler: the context must go straight to the Ollama server, never
# through an HTTP proxy configured in the environment.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OllamaClient:
    def __init__(self, settings: AISettings):
        self.settings = settings

    def analyze(self, context: dict[str, Any]) -> AIResult:
        data = self.post("/api/chat", self.build_request(context))
        return self.to_result(data)

    def build_request(self, context: dict[str, Any]) -> dict[str, Any]:
        schema = report_schema()
        user_message = build_user_message(serialize_context(context))
        return {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": user_message + schema_instructions(json.dumps(schema)),
                },
            ],
            "format": schema,  # Ollama constrains the answer to this schema
            "stream": False,
            "options": {"temperature": 0, "num_ctx": CONTEXT_WINDOW},
        }

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        base = self.settings.ollama_host
        request = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:  # before URLError: it's a subclass
            raise AIError(self.explain_http_error(error)) from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise AIError(self.timeout_message()) from error
            raise AIError(
                f"Ollama is not running at {base}. Start it with: ollama serve"
            ) from error
        except TimeoutError as error:  # timed out while reading the answer
            raise AIError(self.timeout_message()) from error
        except json.JSONDecodeError as error:
            raise AIError("Ollama answered with something that is not JSON.") from error

    def explain_http_error(self, error: urllib.error.HTTPError) -> str:
        detail = error_detail(error)
        model = self.settings.model
        if error.code == 404 and "not found" in detail:
            return (
                f"Model {model!r} is not available in Ollama. Run: ollama pull {model}"
            )
        return f"Ollama returned HTTP {error.code}: {detail or error.reason}"

    def timeout_message(self) -> str:
        return (
            f"Ollama took more than {TIMEOUT_SECONDS:.0f}s to answer. "
            "Try a smaller model with DEVAI_AI_MODEL."
        )

    def to_result(self, data: dict[str, Any]) -> AIResult:
        if data.get("done_reason") == "length":
            raise AIError("The model's answer was cut off before it finished.")
        content = (data.get("message") or {}).get("content", "")
        try:
            report = AIReport.model_validate_json(content)
        except pydantic.ValidationError as error:
            raise AIError(
                "The model's answer did not match the expected report format."
            ) from error
        return AIResult(
            report=report,
            model=data.get("model") or self.settings.model,
            usage=AIUsage(data.get("prompt_eval_count", 0), data.get("eval_count", 0)),
        )


def report_schema() -> dict[str, Any]:
    """AIReport's JSON Schema with every $ref replaced by its definition.

    Support for $defs/$ref in Ollama's `format` is undocumented, so the schema
    is sent flat. (AIReport isn't recursive, so inlining always terminates.)
    """
    schema = AIReport.model_json_schema()
    definitions = schema.get("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(definitions[node["$ref"].rsplit("/", 1)[-1]])
            return {key: inline(value) for key, value in node.items() if key != "$defs"}
        if isinstance(node, list):
            return [inline(item) for item in node]
        return node

    return inline(schema)


def error_detail(error: urllib.error.HTTPError) -> str:
    """The "error" message from Ollama's JSON error body, shortened."""
    try:
        body = json.loads(error.read() or b"{}")
    except (OSError, ValueError):
        return ""
    message = body.get("error", "") if isinstance(body, dict) else ""
    return str(message)[:200]
