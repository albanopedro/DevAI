import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import (
    fake_ai_report,
    fake_docs_proposal,
    fake_fix_proposal,
    fake_generated_tests,
    fake_readme_proposal,
    fake_review_report,
    git_commit,
    write,
)
from fastapi.testclient import TestClient

from devai import cli
from devai.ai.result import AIError, AIResult, AIUsage
from devai.analyzer import analyze_project
from devai.checks import run_checks
from devai.docmap import build_docs_map
from devai.json_report import coverage_to_json, docs_to_json, to_json
from devai.testmap import build_coverage_map
from devai.web import serve as serve_module
from devai.web.app import create_app, load_projects
from devai.web.security import TOKEN_HEADER

TOKEN = "test-token"
BASE = "http://127.0.0.1:8765"
STATS_PY = (
    "def average(values):\n"
    "    return sum(values) / len(values)\n"
    "\n"
    "\n"
    "def percent(part, whole):\n"
    "    return part / whole * 100\n"
)
DOCUMENTED_STATS_PY = (
    '"""Small statistics helpers."""\n'
    "\n"
    "def average(values):\n"
    '    """Return the arithmetic mean of values."""\n'
    "    return sum(values) / len(values)\n"
    "\n"
    "\n"
    "def percent(part, whole):\n"
    '    """Return part as a percentage of whole."""\n'
    "    return part / whole * 100\n"
)


class FakeClient:
    """Stands in for the model: never the network."""

    def __init__(self):
        self.requests = []
        self.result = None
        self.error = None

    def complete(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result

    def answers(self, report):
        self.result = AIResult(report, "fake-model", AIUsage(5, 6))


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(cli, "create_ai_client", lambda settings: client)
    for variable in ("DEVAI_AI_MODEL", "DEVAI_AI_PROVIDER", "OLLAMA_HOST"):
        monkeypatch.delenv(variable, raising=False)
    return client


def web(*roots, dist=None):
    projects = load_projects([str(root) for root in roots])
    app = create_app(projects, TOKEN, dist or Path("/nowhere"))
    return TestClient(app, base_url=BASE, headers={TOKEN_HEADER: TOKEN})


@pytest.fixture
def repo(git_repo):
    write(git_repo, "stats.py", STATS_PY)
    write(git_repo, "tests/test_stats.py", "def test_ok():\n    assert True\n")
    git_commit(git_repo, "fixture")
    return git_repo


def git_state(repo):
    """HEAD and the index: DevAI never commits or stages."""

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True
        ).stdout

    return git("rev-parse", "HEAD"), git("diff", "--cached", "--name-only")


# --- the locks ------------------------------------------------------------------------


def test_the_api_needs_the_token(tmp_path):
    client = web(tmp_path)

    assert client.get("/api/projects", headers={TOKEN_HEADER: ""}).status_code == 401
    wrong = client.get("/api/projects", headers={TOKEN_HEADER: "guess"})
    assert wrong.status_code == 401
    assert wrong.json() == {"detail": "missing or wrong token"}
    assert TestClient(client.app, base_url=BASE).get("/api/projects").status_code == 401


@pytest.mark.parametrize("path", ["/api/projects", "/"])
def test_other_hosts_are_refused(tmp_path, path):
    response = web(tmp_path).get(path, headers={"host": "evil.example:8765"})

    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden host"}


@pytest.mark.parametrize("host", ["localhost:9000", "[::1]:8765", "127.0.0.1"])
def test_local_hosts_on_any_port_work(tmp_path, host):
    assert web(tmp_path).get("/api/projects", headers={"host": host}).status_code == 200


def test_other_origins_are_refused(tmp_path):
    client = web(tmp_path)

    evil = client.post(
        "/api/projects/0/ai",
        json={"task": "analysis"},
        headers={"origin": "http://evil.example"},
    )
    own = client.get("/api/projects", headers={"origin": BASE})

    assert evil.status_code == 403
    assert own.status_code == 200


def test_every_response_has_the_security_headers(tmp_path):
    client = web(tmp_path)

    for response in (
        client.get("/api/projects"),
        client.get("/"),
        client.get("/api/projects", headers={TOKEN_HEADER: "guess"}),
    ):
        assert "default-src 'self'" in response.headers["content-security-policy"]
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-content-type-options"] == "nosniff"


def test_no_other_site_may_read_the_api(tmp_path):
    response = web(tmp_path).options(
        "/api/projects",
        headers={
            "origin": "http://evil.example",
            "access-control-request-method": "GET",
            "access-control-request-headers": TOKEN_HEADER,
        },
    )

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_no_api_documentation_pages(tmp_path, path):
    assert web(tmp_path).get(path).status_code == 404


# --- projects and reports -------------------------------------------------------------


def test_only_the_named_projects(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    client = web(first, second, first)  # named twice: listed once

    assert client.get("/api/projects").json() == [
        {"id": 0, "name": "one", "path": str(first.resolve())},
        {"id": 1, "name": "two", "path": str(second.resolve())},
    ]
    assert client.get("/api/projects/2/analysis").status_code == 404
    assert client.get("/api/projects/-1/analysis").status_code == 404


def test_a_file_is_not_a_project(tmp_path):
    write(tmp_path, "notes.txt", "x")

    with pytest.raises(NotADirectoryError):
        load_projects([str(tmp_path / "notes.txt")])


def test_reports_are_the_same_json_as_the_cli(repo):
    client = web(repo)
    info = analyze_project(repo)

    assert client.get("/api/projects/0/analysis").json() == json.loads(
        to_json(info, run_checks(info))
    )
    assert client.get("/api/projects/0/tests").json() == json.loads(
        coverage_to_json(info.name, build_coverage_map(info))
    )
    assert client.get("/api/projects/0/docs").json() == json.loads(
        docs_to_json(info.name, build_docs_map(info))
    )
    review = client.get("/api/projects/0/review").json()
    assert review["review"]["files"] == []


def test_review_outside_git_explains_why(tmp_path):
    response = web(tmp_path).get("/api/projects/0/review")

    assert response.status_code == 400
    assert "git" in response.json()["detail"]


def test_an_unknown_view(tmp_path):
    assert web(tmp_path).get("/api/projects/0/secrets").status_code == 404


def test_reports_run_nothing_but_git_and_send_nothing(repo, monkeypatch):
    import socket

    real_run = subprocess.run

    def only_git(command, *args, **kwargs):
        assert command[0] == "git", f"unexpected command: {command}"
        return real_run(command, *args, **kwargs)

    def no_network(*args, **kwargs):
        raise AssertionError("network access attempted")

    client = web(repo)
    monkeypatch.setattr(subprocess, "run", only_git)
    # connect, not socket: the test client's event loop needs a local socketpair.
    monkeypatch.setattr(socket.socket, "connect", no_network)

    for view in ("analysis", "review", "tests", "docs"):
        assert client.get(f"/api/projects/0/{view}").status_code == 200


# --- the pages ------------------------------------------------------------------------


def test_without_built_pages_the_api_still_works(tmp_path):
    response = web(tmp_path).get("/")

    assert response.status_code == 200
    assert "the pages aren't built" in response.text


def test_built_pages_are_served_without_the_token(tmp_path):
    dist = tmp_path / "dist"
    write(dist, "index.html", "<!doctype html><title>pages</title>")
    project = tmp_path / "project"
    project.mkdir()
    client = TestClient(
        create_app(load_projects([str(project)]), TOKEN, dist), base_url=BASE
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "<title>pages</title>" in response.text


# --- AI: prepare, send, apply ---------------------------------------------------------


def prepare(client, **body):
    return client.post("/api/projects/0/ai", json=body)


def test_prepare_shows_exactly_what_the_cli_would_send(repo, fake, capsys):
    args = ["--file", "stats.py", "--ai", "--dry-run", "--format", "json"]
    cli.main(["docs", str(repo), *args])
    dry_run = json.loads(capsys.readouterr().out)

    preview = prepare(web(repo), task="docs", file="stats.py").json()

    assert preview["context"] == dry_run
    assert preview["question"].startswith("Send stats.py (~")
    assert preview["leaves_machine"] is True
    assert preview["destination"].startswith("OpenCode (")
    assert preview["tokens"] > 0
    assert fake.requests == []  # nothing was sent


def test_docs_are_sent_checked_and_applied_after_two_clicks(repo, fake):
    fake.answers(fake_docs_proposal())
    client = web(repo)
    before = git_state(repo)

    prepared = prepare(client, task="docs", file="stats.py").json()
    answer = client.post(f"/api/prepared/{prepared['prepared_id']}/send").json()

    assert answer["result"]["ai"]["added"] == ["(module)", "average", "percent"]
    assert answer["result"]["ai"]["diff"].startswith("--- a/stats.py")
    assert answer["apply"]["kind"] == "write"
    assert answer["apply"]["files"] == ["stats.py"]
    assert answer["apply"]["blocked"] is None
    assert (repo / "stats.py").read_text() == STATS_PY  # sent, not written

    applied = client.post(f"/api/outcomes/{answer['apply']['outcome_id']}/apply")

    assert applied.json() == {
        "applied": True,
        "files": ["stats.py"],
        "undo": "git restore stats.py",
    }
    assert (repo / "stats.py").read_text() == DOCUMENTED_STATS_PY
    assert git_state(repo) == before


def test_the_page_cant_choose_what_is_written(repo, fake):
    fake.answers(fake_docs_proposal())
    client = web(repo)
    prepared = prepare(client, task="docs", file="stats.py").json()
    answer = client.post(f"/api/prepared/{prepared['prepared_id']}/send").json()

    client.post(
        f"/api/outcomes/{answer['apply']['outcome_id']}/apply",
        json={"content": "import os; os.system('evil')", "path": "evil.py"},
    )

    assert (repo / "stats.py").read_text() == DOCUMENTED_STATS_PY
    assert not (repo / "evil.py").exists()


def test_each_preview_is_sent_once_and_each_answer_applied_once(repo, fake):
    fake.answers(fake_docs_proposal())
    client = web(repo)
    prepared = prepare(client, task="docs", file="stats.py").json()
    send = f"/api/prepared/{prepared['prepared_id']}/send"
    answer = client.post(send).json()
    apply = f"/api/outcomes/{answer['apply']['outcome_id']}/apply"
    client.post(apply)

    assert client.post(send).status_code == 404
    assert client.post(apply).status_code == 404
    assert client.post("/api/prepared/made-up/send").status_code == 404
    assert len(fake.requests) == 1


def test_a_file_changed_after_the_answer_is_not_overwritten(repo, fake):
    fake.answers(fake_docs_proposal())
    client = web(repo)
    prepared = prepare(client, task="docs", file="stats.py").json()
    answer = client.post(f"/api/prepared/{prepared['prepared_id']}/send").json()
    write(repo, "stats.py", STATS_PY + "\n# edited meanwhile\n")

    response = client.post(f"/api/outcomes/{answer['apply']['outcome_id']}/apply")

    assert response.status_code == 409
    assert "uncommitted changes" in response.json()["detail"]
    assert (repo / "stats.py").read_text().endswith("# edited meanwhile\n")


def test_uncommitted_changes_block_apply_before_the_click(repo, fake):
    write(repo, "stats.py", STATS_PY + "\n# work in progress\n")
    docs = [("average", "Return the mean.")]
    fake.answers(fake_docs_proposal(docs))
    client = web(repo)
    prepared = prepare(client, task="docs", file="stats.py").json()

    answer = client.post(f"/api/prepared/{prepared['prepared_id']}/send").json()

    assert "uncommitted changes" in answer["apply"]["blocked"]


def test_an_unsafe_answer_is_rejected_and_offers_nothing_to_apply(repo, fake):
    fake.answers(fake_docs_proposal([("average", 'Mean."""\nimport os\n"""')]))
    client = web(repo)
    prepared = prepare(client, task="docs", file="stats.py").json()

    answer = client.post(f"/api/prepared/{prepared['prepared_id']}/send").json()

    assert 'contain """' in answer["result"]["ai"]["rejected"]
    assert "apply" not in answer


def test_an_ai_failure_changes_nothing(repo, fake):
    fake.error = AIError("the free model is busy")
    client = web(repo)
    prepared = prepare(client, task="docs", file="stats.py").json()

    response = client.post(f"/api/prepared/{prepared['prepared_id']}/send")

    assert response.status_code == 502
    assert "the free model is busy" in response.json()["detail"]
    assert (repo / "stats.py").read_text() == STATS_PY


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"task": "magic"}, "unknown task"),
        ({"task": "docs"}, "'file' is required"),
        ({"task": "docs", "file": "../outside.py"}, "outside the project"),
        ({"task": "docs", "file": "missing.py"}, "no such file"),
        ({"task": "docs", "file": "tests/test_stats.py"}, "not tests or config"),
        ({"task": "fix", "ask": "x", "files": []}, "name 1 to 3 files"),
        ({"task": "fix", "ask": "", "files": ["stats.py"]}, "'ask' is required"),
        ({"task": "analysis", "provider": "paid"}, "must be one of"),
    ],
)
def test_requests_that_cant_be_prepared(repo, fake, body, message):
    response = prepare(web(repo), **body)

    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert fake.requests == []


def test_analysis_and_review_have_nothing_to_apply(repo, fake):
    client = web(repo)
    fake.answers(fake_ai_report())
    prepared = prepare(client, task="analysis").json()
    analysis = client.post(f"/api/prepared/{prepared['prepared_id']}/send").json()

    write(repo, "stats.py", STATS_PY + "\n\ndef median(values):\n    return 0\n")
    fake.answers(fake_review_report(issues=[]))
    prepared = prepare(client, task="review").json()
    review = client.post(f"/api/prepared/{prepared['prepared_id']}/send").json()

    assert analysis["result"]["ai"]["report"]["summary"].startswith("A small Python")
    assert "apply" not in analysis
    assert review["result"]["ai"]["report"]["issues"] == []
    assert "apply" not in review


def test_review_needs_changes_to_send(repo, fake):
    response = prepare(web(repo), task="review")

    assert response.status_code == 400
    assert "no code changes" in response.json()["detail"]


def test_a_fix_is_written_after_the_click(repo, fake):
    fake.answers(fake_fix_proposal())
    client = web(repo)
    prepared = prepare(client, task="fix", ask="handle zero", files=["stats.py"])

    answer = client.post(f"/api/prepared/{prepared.json()['prepared_id']}/send")
    client.post(f"/api/outcomes/{answer.json()['apply']['outcome_id']}/apply")

    assert (
        'raise ValueError("whole must not be zero")' in (repo / "stats.py").read_text()
    )


def test_new_tests_are_created_never_overwritten(repo, fake):
    fake.answers(fake_generated_tests())
    client = web(repo)
    prepared = prepare(client, task="tests", file="stats.py").json()
    answer = client.post(f"/api/prepared/{prepared['prepared_id']}/send").json()

    assert answer["apply"]["kind"] == "create"
    assert answer["result"]["run_command"].startswith("pytest tests/")
    applied = client.post(f"/api/outcomes/{answer['apply']['outcome_id']}/apply")

    assert applied.json()["undo"] == "rm tests/test_stats_edge_cases.py"
    assert (
        "def test_percent_of_zero_whole_raises"
        in (repo / "tests/test_stats_edge_cases.py").read_text()
    )


def test_a_test_file_that_appeared_meanwhile_is_kept(repo, fake):
    fake.answers(fake_generated_tests())
    client = web(repo)
    prepared = prepare(client, task="tests", file="stats.py").json()
    answer = client.post(f"/api/prepared/{prepared['prepared_id']}/send").json()
    write(repo, "tests/test_stats_edge_cases.py", "# mine\n")

    response = client.post(f"/api/outcomes/{answer['apply']['outcome_id']}/apply")

    assert response.status_code == 409
    assert (repo / "tests/test_stats_edge_cases.py").read_text() == "# mine\n"


def test_a_new_readme_is_created(repo, fake):
    sections = [("usage", "Usage", "Import `stats` and call `average`.")]
    fake.answers(fake_readme_proposal(sections, description="Statistics helpers."))
    client = web(repo)
    prepared = prepare(client, task="readme").json()
    assert prepared["context"]["topics"] == ["installation", "usage", "tests"]

    answer = client.post(f"/api/prepared/{prepared['prepared_id']}/send").json()
    client.post(f"/api/outcomes/{answer['apply']['outcome_id']}/apply")

    assert answer["result"]["left_out"] == [
        {
            "topic": "license",
            "reason": "choosing a license is your decision: add a LICENSE file",
        }
    ]
    assert (
        (repo / "README.md")
        .read_text()
        .startswith(f"# {repo.name}\n\nStatistics helpers.\n\n## Usage\n")
    )


# --- starting the server --------------------------------------------------------------


def test_serve_listens_on_this_computer_only(tmp_path, capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(serve_module.uvicorn, "run", lambda app, **kw: calls.append(kw))

    assert cli.main(["serve", str(tmp_path), "--port", "9876", "--no-open"]) == 0

    out = capsys.readouterr().out
    assert calls == [
        {"host": "127.0.0.1", "port": 9876, "log_level": "warning", "access_log": False}
    ]
    assert f"DevAI is serving {tmp_path.name}, for this computer only." in out
    assert "Open: http://127.0.0.1:9876/?token=" in out


def test_listen_all_is_for_containers(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(serve_module.uvicorn, "run", lambda app, **kw: calls.append(kw))

    cli.main(["serve", str(tmp_path), "--listen-all", "--no-open"])

    assert calls[0]["host"] == "0.0.0.0"


def test_each_run_has_a_new_token(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(serve_module.uvicorn, "run", lambda app, **kw: None)

    cli.main(["serve", str(tmp_path), "--no-open"])
    cli.main(["serve", str(tmp_path), "--no-open"])

    urls = [line for line in capsys.readouterr().out.splitlines() if "token=" in line]
    assert len(urls) == 2 and urls[0] != urls[1]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["serve", "missing-dir", "--no-open"], "not a directory: missing-dir"),
        (["serve", ".", "--port", "0", "--no-open"], "--port must be between"),
    ],
)
def test_serve_usage_errors(args, message, capsys, monkeypatch):
    monkeypatch.setattr(serve_module.uvicorn, "run", lambda app, **kw: None)

    assert cli.main(args) == cli.EXIT_USAGE
    assert message in capsys.readouterr().err


def test_serve_without_the_web_extra(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(sys.modules, "devai.web.serve", None)  # as if not installed

    assert cli.main(["serve", str(tmp_path)]) == cli.EXIT_USAGE
    assert "pip install 'devai[web]'" in capsys.readouterr().err
