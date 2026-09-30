"""Run the AI analysis through the user's own OpenCode CLI, with a free model.

OpenCode's free models may only be used from within OpenCode, so DevAI
calls `opencode run` instead of the service's HTTP API (D033). The run is
locked down so the model sees only the AI context (D025):

- an inline config (OPENCODE_CONFIG_CONTENT) defines a `devai` agent with
  DevAI's system prompt and every permission denied: no files, no commands;
- the run happens in an empty temporary directory, deleted afterwards;
- only free `opencode/...` models are accepted (settings.py), and a run that
  reports any cost is treated as an error: DevAI must be free (D032).
"""

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any

import pydantic

from devai.ai.context import serialize_context
from devai.ai.prompt import SYSTEM_PROMPT, build_user_message, schema_instructions
from devai.ai.result import AIError, AIResult, AIUsage
from devai.ai.schema import AIReport, report_schema
from devai.ai.settings import AISettings

TIMEOUT_SECONDS = 300.0
AGENT_NAME = "devai"
SESSION_TITLE = "DevAI analysis"


@dataclass
class RunOutput:
    """What DevAI needs from the `opencode run --format json` events."""

    texts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    finish_reason: str | None = None


class OpenCodeClient:
    def __init__(self, settings: AISettings, executable: str | None = None):
        self.settings = settings
        self.executable = executable  # None: find `opencode` on PATH

    def analyze(self, context: dict[str, Any]) -> AIResult:
        executable = self.executable or shutil.which("opencode")
        if executable is None:
            raise AIError(
                "OpenCode is not installed. Install it with: brew install opencode "
                "(or see opencode.ai), or use --provider ollama."
            )

        message = build_user_message(serialize_context(context)) + schema_instructions(
            json.dumps(report_schema())
        )
        env = os.environ | {"OPENCODE_CONFIG_CONTENT": json.dumps(inline_config())}
        with tempfile.TemporaryDirectory(prefix="devai-opencode-") as empty_dir:
            command = [
                executable,
                "run",
                "--model",
                self.settings.model,
                "--agent",
                AGENT_NAME,
                "--format",
                "json",
                "--dir",
                empty_dir,
                "--title",
                SESSION_TITLE,
                message,
            ]
            try:
                completed = subprocess.run(
                    command,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_SECONDS,
                    stdin=subprocess.DEVNULL,
                )
            except subprocess.TimeoutExpired as error:
                raise AIError(
                    f"OpenCode took more than {TIMEOUT_SECONDS:.0f}s to answer."
                ) from error

        if completed.returncode != 0:
            raise AIError(explain_failure(completed.stderr or completed.stdout))
        return self.to_result(parse_events(completed.stdout))

    def to_result(self, run: RunOutput) -> AIResult:
        if run.errors:
            raise AIError(explain_failure(run.errors[-1]))
        if run.cost > 0:
            # Free models report a cost of 0. Anything else breaks DevAI's rule.
            raise AIError(
                f"OpenCode reported a cost of {run.cost} for this run. DevAI only "
                "uses free models, so it stopped. Check DEVAI_AI_MODEL."
            )
        if run.finish_reason == "length":
            raise AIError("The model's answer was cut off before it finished.")
        if not run.texts:
            raise AIError("OpenCode returned no answer.")

        try:
            report = AIReport.model_validate_json(strip_code_fence(run.texts[-1]))
        except pydantic.ValidationError as error:
            raise AIError(
                "The model's answer did not match the expected report format. "
                "Try another free model with DEVAI_AI_MODEL."
            ) from error
        return AIResult(
            report=report,
            model=self.settings.model,
            usage=AIUsage(run.input_tokens, run.output_tokens),
        )


def inline_config() -> dict[str, Any]:
    """OpenCode config for this run only: a `devai` agent that can't use tools."""
    return {
        "permission": {"*": "deny"},
        "agent": {
            AGENT_NAME: {
                "mode": "primary",
                "description": "DevAI project analysis (no tools)",
                "prompt": SYSTEM_PROMPT,
                "permission": {"*": "deny"},
            }
        },
    }


def parse_events(stdout: str) -> RunOutput:
    """Read the JSON event lines: text parts, step totals, errors."""
    run = RunOutput()
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # not an event (e.g. a log line)
        if not isinstance(event, dict):
            continue
        part = event.get("part") or {}
        kind = event.get("type")
        if kind == "text" and isinstance(part.get("text"), str):
            run.texts.append(part["text"])
        elif kind == "step_finish":
            tokens = part.get("tokens") or {}
            run.input_tokens += int(tokens.get("input", 0))
            # Reasoning tokens are output the model generated, too.
            run.output_tokens += int(tokens.get("output", 0)) + int(
                tokens.get("reasoning", 0)
            )
            run.cost += float(part.get("cost") or 0)
            run.finish_reason = part.get("reason")
        elif kind == "error":
            run.errors.append(json.dumps(event.get("error") or event))
    return run


def strip_code_fence(text: str) -> str:
    """Accept an answer wrapped in ```json ... ``` as well as plain JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return text.strip()


def explain_failure(output: str) -> str:
    """A short, user-facing reason for a failed run."""
    lowered = output.lower()
    if "freetiererror" in lowered or "free tier" in lowered:
        return (
            "OpenCode's free tier refused this request. Try another free model "
            "with DEVAI_AI_MODEL, or use --provider ollama."
        )
    if "429" in output or "rate limit" in lowered or "freeusagelimit" in lowered:
        return (
            "OpenCode's free usage limit was reached. Try again later, "
            "or use --provider ollama."
        )
    last_line = next(
        (line for line in reversed(output.strip().splitlines()) if line.strip()), ""
    )
    detail = "".join(char if char.isprintable() else " " for char in last_line)
    return f"OpenCode failed: {detail[:200] or 'no details'}"
