import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import fake_ai_report

from devai.ai import ollama_client
from devai.ai.analysis import analysis_request
from devai.ai.context import serialize_context
from devai.ai.ollama_client import OllamaClient
from devai.ai.prompt import SYSTEM_PROMPT, build_user_message
from devai.ai.result import AIError, AIUsage
from devai.ai.schema import AIReport, flat_schema
from devai.ai.settings import AISettings

CONTEXT = {"context_version": 1, "project": {"name": "demo"}, "findings": []}
REQUEST = analysis_request(CONTEXT)


class StubOllama:
    """A tiny HTTP server that plays Ollama: records requests, sends canned replies."""

    def __init__(self):
        self.requests = []
        self.status = 200
        self.body = None
        self.delay = 0.0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                stub.requests.append((self.path, json.loads(self.rfile.read(length))))
                time.sleep(stub.delay)
                payload = (
                    stub.body
                    if isinstance(stub.body, bytes)
                    else json.dumps(stub.body).encode()
                )
                self.send_response(stub.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):  # keep test output quiet
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        # A short poll interval makes shutdown() quick (the default waits 0.5s).
        threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        ).start()

    def reply(self, report=None, **fields):
        self.body = {
            "model": "qwen3.5:9b",
            "message": {
                "role": "assistant",
                "content": (report or fake_ai_report()).model_dump_json(),
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 900,
            "eval_count": 450,
        } | fields


@pytest.fixture
def ollama():
    stub = StubOllama()
    stub.reply()
    yield stub
    stub.server.shutdown()
    stub.server.server_close()


def client_for(stub, model="qwen3.5:9b"):
    return OllamaClient(
        AISettings(model=model, provider="ollama", ollama_host=stub.url)
    )


# --- the request -------------------------------------------------------------


def test_request_sends_the_same_context_and_the_schema(ollama):
    client_for(ollama).complete(REQUEST)

    [(path, body)] = ollama.requests
    assert path == "/api/chat"
    assert body["model"] == "qwen3.5:9b"
    assert body["stream"] is False
    assert body["format"] == flat_schema(AIReport)
    assert body["options"] == {"temperature": 0, "num_ctx": 16_384}
    system, user = body["messages"]
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert user["role"] == "user"
    assert user["content"].startswith(build_user_message(serialize_context(CONTEXT)))
    assert "Answer with JSON that follows this schema" in user["content"]


def test_schema_is_flat():
    text = json.dumps(flat_schema(AIReport))

    assert "$ref" not in text and "$defs" not in text
    risk = flat_schema(AIReport)["properties"]["risks"]["items"]
    assert risk["properties"]["severity"]["enum"] == ["high", "medium", "low"]


def test_result_is_parsed_and_validated(ollama):
    result = client_for(ollama).complete(REQUEST)

    assert result.report == fake_ai_report()
    assert result.model == "qwen3.5:9b"
    assert result.usage == AIUsage(900, 450)


def test_http_proxy_settings_are_ignored(ollama, monkeypatch):
    # The context must go straight to Ollama, never through a proxy.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")

    client_for(ollama).complete(REQUEST)

    assert len(ollama.requests) == 1


# --- failures ----------------------------------------------------------------


def test_missing_model(ollama):
    ollama.status = 404
    ollama.body = {"error": 'model "qwen3.5:9b" not found, try pulling it first'}

    with pytest.raises(AIError, match=r"Run: ollama pull qwen3\.5:9b"):
        client_for(ollama).complete(REQUEST)


def test_other_http_errors(ollama):
    ollama.status = 500
    ollama.body = {"error": "out of memory"}

    with pytest.raises(AIError, match="HTTP 500: out of memory"):
        client_for(ollama).complete(REQUEST)


def test_ollama_not_running():
    with socket.socket() as sock:  # grab a free port, then leave it closed
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    settings = AISettings(provider="ollama", ollama_host=f"http://127.0.0.1:{port}")

    with pytest.raises(AIError, match="Ollama is not running.*ollama serve"):
        OllamaClient(settings).complete(REQUEST)


def test_timeout(ollama, monkeypatch):
    monkeypatch.setattr(ollama_client, "TIMEOUT_SECONDS", 0.2)
    ollama.delay = 1.0

    with pytest.raises(AIError, match="took more than"):
        client_for(ollama).complete(REQUEST)


def test_answer_not_matching_the_schema(ollama):
    ollama.body["message"]["content"] = '{"summary": "only this"}'

    with pytest.raises(AIError, match="did not match the expected report format"):
        client_for(ollama).complete(REQUEST)


def test_answer_cut_off(ollama):
    ollama.body["done_reason"] = "length"

    with pytest.raises(AIError, match="cut off"):
        client_for(ollama).complete(REQUEST)


def test_response_that_is_not_json(ollama):
    ollama.body = b"<html>not ollama</html>"

    with pytest.raises(AIError, match="not JSON"):
        client_for(ollama).complete(REQUEST)
