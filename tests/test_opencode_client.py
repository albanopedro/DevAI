import json
import os
import sys

import pytest
from conftest import fake_ai_report

from devai.ai import opencode_client
from devai.ai.analysis import analysis_request
from devai.ai.context import serialize_context
from devai.ai.opencode_client import OpenCodeClient, inline_config, parse_events
from devai.ai.prompt import SYSTEM_PROMPT, build_user_message
from devai.ai.result import AIError, AIUsage
from devai.ai.settings import AISettings

CONTEXT = {"context_version": 1, "project": {"name": "demo"}, "findings": []}
REQUEST = analysis_request(CONTEXT)

# A stand-in for the `opencode` executable: records how it was called, then
# prints the canned output described in $FAKE_OPENCODE_SPEC.
FAKE_OPENCODE = """\
import json, os, sys, time
spec = json.load(open(os.environ["FAKE_OPENCODE_SPEC"]))
args = sys.argv[1:]
work_dir = args[args.index("--dir") + 1]
with open(os.environ["FAKE_OPENCODE_LOG"], "w") as log:
    json.dump({
        "args": args,
        "config": os.environ.get("OPENCODE_CONFIG_CONTENT"),
        "dir_was_empty": os.listdir(work_dir) == [],
    }, log)
time.sleep(spec.get("sleep", 0))
sys.stdout.write(spec.get("stdout", ""))
sys.stderr.write(spec.get("stderr", ""))
sys.exit(spec.get("exit", 0))
"""


def events(text=None, tokens=None, cost=0, reason="stop", extra=()):
    """JSON event lines shaped like a real `opencode run --format json`."""
    lines = [{"type": "step_start", "part": {"type": "step-start"}}]
    if text is not None:
        lines.append({"type": "text", "part": {"type": "text", "text": text}})
    lines.extend(extra)
    lines.append(
        {
            "type": "step_finish",
            "part": {
                "type": "step-finish",
                "reason": reason,
                "tokens": tokens or {"input": 1128, "output": 582, "reasoning": 429},
                "cost": cost,
            },
        }
    )
    return "".join(json.dumps(line) + "\n" for line in lines)


class FakeOpenCode:
    def __init__(self, tmp_path, monkeypatch):
        self.executable = tmp_path / "opencode"
        self.executable.write_text(f"#!{sys.executable}\n{FAKE_OPENCODE}")
        self.executable.chmod(0o755)
        self.spec_file = tmp_path / "spec.json"
        self.log_file = tmp_path / "log.json"
        monkeypatch.setenv("FAKE_OPENCODE_SPEC", str(self.spec_file))
        monkeypatch.setenv("FAKE_OPENCODE_LOG", str(self.log_file))
        self.reply(stdout=events(fake_ai_report().model_dump_json()))

    def reply(self, **spec):
        self.spec_file.write_text(json.dumps(spec))

    @property
    def call(self):
        return json.loads(self.log_file.read_text())


@pytest.fixture
def opencode(tmp_path, monkeypatch):
    return FakeOpenCode(tmp_path, monkeypatch)


def client_for(fake, model="opencode/space-bunny-free"):
    return OpenCodeClient(AISettings(model=model), executable=str(fake.executable))


# --- how OpenCode is called --------------------------------------------------


def test_runs_the_free_model_with_the_devai_agent(opencode):
    client_for(opencode).complete(REQUEST)

    args = opencode.call["args"]
    assert args[0] == "run"
    assert args[args.index("--model") + 1] == "opencode/space-bunny-free"
    assert args[args.index("--agent") + 1] == "devai"
    assert args[args.index("--format") + 1] == "json"
    assert args[args.index("--title") + 1] == "DevAI analysis"


def test_sends_only_the_context_and_the_schema(opencode):
    client_for(opencode).complete(REQUEST)

    message = opencode.call["args"][-1]
    assert message.startswith(build_user_message(serialize_context(CONTEXT)))
    assert "Answer with JSON that follows this schema" in message


def test_every_permission_is_denied(opencode):
    client_for(opencode).complete(REQUEST)

    config = json.loads(opencode.call["config"])
    assert config == inline_config(SYSTEM_PROMPT)
    assert config["permission"] == {"*": "deny"}
    agent = config["agent"]["devai"]
    assert agent["permission"] == {"*": "deny"}
    assert agent["prompt"] == SYSTEM_PROMPT


def test_runs_in_an_empty_directory_that_is_removed(opencode):
    client_for(opencode).complete(REQUEST)

    args = opencode.call["args"]
    work_dir = args[args.index("--dir") + 1]
    assert opencode.call["dir_was_empty"] is True
    assert not os.path.exists(work_dir)  # deleted after the run


# --- reading the answer ------------------------------------------------------


def test_result_is_validated_and_counts_reasoning_as_output(opencode):
    result = client_for(opencode).complete(REQUEST)

    assert result.report == fake_ai_report()
    assert result.model == "opencode/space-bunny-free"
    assert result.usage == AIUsage(1128, 582 + 429)


def test_answer_in_a_code_fence_is_accepted(opencode):
    fenced = "```json\n" + fake_ai_report().model_dump_json() + "\n```"
    opencode.reply(stdout=events(fenced))

    assert client_for(opencode).complete(REQUEST).report == fake_ai_report()


def test_last_text_part_is_the_answer():
    stdout = events(
        "thinking out loud",
        extra=[{"type": "text", "part": {"type": "text", "text": "final answer"}}],
    )

    assert parse_events(stdout).texts[-1] == "final answer"


def test_non_json_lines_are_ignored():
    stdout = "some log line\n" + events("answer")

    assert parse_events(stdout).texts == ["answer"]


# --- the primordial rule: never pay ------------------------------------------


def test_a_run_that_reports_a_cost_is_an_error(opencode):
    opencode.reply(stdout=events(fake_ai_report().model_dump_json(), cost=0.0042))

    with pytest.raises(
        AIError, match="reported a cost of 0.0042.*only uses free models"
    ):
        client_for(opencode).complete(REQUEST)


# --- failures ----------------------------------------------------------------


def test_opencode_not_installed(monkeypatch):
    monkeypatch.setenv("PATH", "")

    with pytest.raises(
        AIError, match="OpenCode is not installed.*brew install opencode"
    ):
        OpenCodeClient(AISettings()).complete(REQUEST)


def test_free_tier_refusal(opencode):
    opencode.reply(
        stderr="Error: FreeTierError: OpenCode's free tier can only be used "
        "from within OpenCode\n",
        exit=1,
    )

    with pytest.raises(AIError, match="free tier refused.*--provider ollama"):
        client_for(opencode).complete(REQUEST)


def test_free_usage_limit(opencode):
    opencode.reply(stderr="Error: 429 Too Many Requests\n", exit=1)

    with pytest.raises(AIError, match="free usage limit was reached"):
        client_for(opencode).complete(REQUEST)


def test_other_failures_show_the_last_line(opencode):
    opencode.reply(stderr="starting\nError: model not found\x1b[0m\n", exit=1)

    with pytest.raises(AIError, match="OpenCode failed: Error: model not found"):
        client_for(opencode).complete(REQUEST)


def test_error_event(opencode):
    opencode.reply(
        stdout=events(extra=[{"type": "error", "error": {"name": "ProviderAuthError"}}])
    )

    with pytest.raises(AIError, match="OpenCode failed: .*ProviderAuthError"):
        client_for(opencode).complete(REQUEST)


def test_timeout(opencode, monkeypatch):
    monkeypatch.setattr(opencode_client, "TIMEOUT_SECONDS", 0.5)
    opencode.reply(sleep=3)

    with pytest.raises(AIError, match="took more than"):
        client_for(opencode).complete(REQUEST)


def test_answer_cut_off(opencode):
    opencode.reply(stdout=events('{"summary": "trunc', reason="length"))

    with pytest.raises(AIError, match="cut off"):
        client_for(opencode).complete(REQUEST)


def test_no_answer(opencode):
    opencode.reply(stdout=events())

    with pytest.raises(AIError, match="no answer"):
        client_for(opencode).complete(REQUEST)


def test_answer_not_matching_the_schema(opencode):
    opencode.reply(stdout=events('{"summary": "only this"}'))

    with pytest.raises(AIError, match="did not match.*another free model"):
        client_for(opencode).complete(REQUEST)
