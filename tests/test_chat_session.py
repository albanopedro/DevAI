import json
import re

import pytest
from conftest import fake_chat_answer, write

from devai.ai.result import AIError, AIResult, AIUsage
from devai.ai.settings import AISettings
from devai.analyzer import analyze_project
from devai.chat.session import ChatSession
from devai.checks import run_checks


class FakeClient:
    def __init__(self):
        self.requests = []
        self.error = None

    def complete(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return AIResult(fake_chat_answer(), "fake-model", AIUsage(5, 6))

    def context(self, index=0):
        message = self.requests[index].message
        match = re.search(r"<chat_context>\n(.*)\n</chat_context>", message, re.DOTALL)
        return json.loads(match.group(1))

    def sent_paths(self, index=0):
        return [file["path"] for file in self.context(index)["files"]]


@pytest.fixture
def project(tmp_path):
    write(tmp_path, "api/users.py", "def get_user():\n    raise Error(500)\n")
    write(tmp_path, "api/db.py", "def connect():\n    pass\n")
    write(tmp_path, "README.md", "users api\n")
    return tmp_path


def chat(project, typed, settings=None, assume_yes=False):
    """Run a session where the user types `typed` (None = Ctrl+D)."""
    lines = list(typed)
    output = []
    prompts = []
    client = FakeClient()

    def read_line(prompt):
        prompts.append(prompt)
        return lines.pop(0) if lines else None

    info = analyze_project(project)
    session = ChatSession(
        info,
        run_checks(info),
        client,
        settings or AISettings(),
        read_line,
        output.append,
        assume_yes,
    )
    session.run()
    return client, "\n".join(output), prompts, session


# --- approving what is sent ------------------------------------------------------


def test_approved_question_is_answered(project):
    client, out, prompts, _ = chat(project, ["users 500", "y", "/quit"])

    assert len(client.requests) == 1
    assert client.sent_paths() == ["api/users.py", "README.md"]
    assert "  1. api/users.py  matches: users, 500  (2 lines)" in out
    assert "get_user raises Error(500)" in out
    assert any("Files: api/users.py, README.md. [y]es / [n]o" in p for p in prompts)


@pytest.mark.parametrize("reply", ["n", "", "no", None])
def test_anything_but_yes_sends_nothing(project, reply):
    client, out, _, _ = chat(project, ["users 500", reply, "/quit"])

    assert client.requests == []


def test_drop_a_file_for_this_question(project):
    client, out, _, _ = chat(project, ["users 500", "drop 2", "y", "/quit"])

    assert client.sent_paths() == ["api/users.py"]
    assert "Dropped README.md for this question." in out


def test_add_a_file_for_this_question(project):
    client, _, _, _ = chat(project, ["users 500", "add api/db.py", "y", "/quit"])

    assert client.sent_paths() == ["api/users.py", "README.md", "api/db.py"]
    assert client.context()["files"][2]["reason"] == "added by you"


def test_unknown_reply_asks_again(project):
    client, out, _, _ = chat(project, ["users 500", "maybe", "y", "/quit"])

    assert "Please answer [y]es / [n]o / drop N / add PATH." in out
    assert len(client.requests) == 1


def test_assume_yes_skips_the_question(project):
    client, _, prompts, _ = chat(project, ["users 500", "/quit"], assume_yes=True)

    assert len(client.requests) == 1
    assert not any("[y]es" in prompt for prompt in prompts)


def test_local_ollama_does_not_ask(project):
    settings = AISettings(model="qwen3.5:9b", provider="ollama")

    client, out, prompts, _ = chat(project, ["users 500", "/quit"], settings)

    assert len(client.requests) == 1
    assert "Asking qwen3.5:9b locally (nothing leaves this machine)…" in out


# --- pinned files --------------------------------------------------------------------


def test_add_pins_a_file_for_every_next_question(project):
    client, out, _, session = chat(
        project, ["/add api/db.py", "users", "y", "/files", "/quit"]
    )

    assert client.sent_paths()[0] == "api/db.py"
    assert client.context()["files"][0]["reason"] == "added with /add"
    assert "Files added with /add: api/db.py" in out


def test_drop_unpins(project):
    client, out, _, session = chat(
        project, ["/add api/db.py", "/drop api/db.py", "users", "y", "/quit"]
    )

    assert "api/db.py" not in client.sent_paths()
    assert session.pinned == []


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("../outside.py", "outside the project"),
        (".env", "never sent"),
        ("", "Which file?"),
    ],
)
def test_add_gets_the_same_checks_as_file(project, name, message):
    write(project.parent, "outside.py", "x = 1\n")
    write(project, ".env", "SECRET=1\n")

    _, out, _, session = chat(project, [f"/add {name}".strip(), "/quit"])

    assert message in out
    assert session.pinned == []


# --- conversation history -------------------------------------------------------------


def test_second_question_carries_the_first_exchange(project):
    client, _, _, _ = chat(
        project, ["users 500", "y", "and the database?", "y", "/quit"]
    )

    assert client.context(0)["history"] == []
    first_answer = fake_chat_answer().answer
    assert client.context(1)["history"] == [
        {"question": "users 500", "answer": first_answer}
    ]


def test_clear_forgets_the_conversation(project):
    client, out, _, _ = chat(
        project, ["users 500", "y", "/clear", "and the database?", "y", "/quit"]
    )

    assert client.context(1)["history"] == []
    assert "Conversation cleared" in out


def test_declined_question_is_not_remembered(project):
    client, _, _, session = chat(project, ["users 500", "n", "/quit"])

    assert session.history == []


# --- leaving, help, errors ----------------------------------------------------


def test_ctrl_d_at_the_prompt_leaves(project):
    client, out, _, _ = chat(project, [None])

    assert client.requests == []
    assert out.startswith("DEVAI CHAT · ")


def test_help_and_unknown_commands(project):
    _, out, _, _ = chat(project, ["/help", "/nope", "/quit"])

    assert "/add PATH    send this file with every next question" in out
    assert "Unknown command /nope. Type /help." in out


def test_ai_failure_keeps_the_chat_going(project):
    def run(client_error):
        lines = ["users 500", "y", "users again", "y", "/quit"]
        output = []
        info = analyze_project(project)
        client = FakeClient()
        client.error = client_error
        session = ChatSession(
            info,
            run_checks(info),
            client,
            AISettings(),
            lambda prompt: lines.pop(0) if lines else None,
            output.append,
        )
        session.run()
        return client, "\n".join(output)

    client, out = run(AIError("OpenCode is not installed."))

    assert len(client.requests) == 2  # the session continued after the error
    assert out.count("AI chat failed: OpenCode is not installed.") == 2


def test_banner_names_the_destination_and_data_note(project):
    settings = AISettings(model="opencode/big-pickle")

    _, out, _, _ = chat(project, ["/quit"], settings)

    assert "Answers come from OpenCode (opencode/big-pickle, free model)." in out
    assert "Note: this free model may use your data to improve it." in out
