"""The local API and the built pages (D051).

Every response passes the Host check; every /api request also needs the token
and, from a browser, the page's own origin. There is no CORS: no other site
may read anything. Views are the same JSON as the CLI's --format json.
"""

import os
import secrets
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from devai import __version__
from devai.ai.result import AIError
from devai.ai.settings import SettingsError, load_settings
from devai.analyzer import analyze_project
from devai.checks import run_checks
from devai.docmap import build_docs_map
from devai.json_report import coverage_to_json, docs_to_json, review_to_json, to_json
from devai.review import ReviewError, collect_changes, review_report, run_review_checks
from devai.testmap import build_coverage_map
from devai.web import tasks
from devai.web.security import (
    SECURITY_HEADERS,
    TOKEN_HEADER,
    host_allowed,
    origin_allowed,
    token_matches,
)

VIEWS = ("analysis", "review", "tests", "docs")
MAX_KEPT = 50  # prepared requests and outcomes kept in memory


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    path: Path


def load_projects(paths: list[str]) -> list[Project]:
    """The projects the pages may open: only these, named on the command line."""
    projects: list[Project] = []
    for given in paths:
        path = Path(given).expanduser().resolve()
        if not path.is_dir():
            raise NotADirectoryError(given)
        if all(project.path != path for project in projects):
            projects.append(Project(len(projects), path.name, path))
    return projects


class Kept:
    """Server-side memory with random ids: a page can name an item, not forge one."""

    def __init__(self, limit: int = MAX_KEPT) -> None:
        self.items: OrderedDict[str, Any] = OrderedDict()
        self.limit = limit

    def put(self, item: Any) -> str:
        key = secrets.token_urlsafe(16)
        self.items[key] = item
        while len(self.items) > self.limit:
            self.items.popitem(last=False)
        return key

    def pop(self, key: str) -> Any:
        """Take an item out: each preview is sent once, each outcome applied once."""
        if key not in self.items:
            raise HTTPException(404, "not found, or already used: start again")
        return self.items.pop(key)


class PrepareBody(BaseModel):
    task: str
    provider: str | None = None
    file: str | None = None
    files: list[str] = []
    ask: str | None = None


def web_dist() -> Path:
    """Where the built pages are: $DEVAI_WEB_DIST, or web/dist in a checkout."""
    configured = os.environ.get("DEVAI_WEB_DIST")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app(
    projects: list[Project], token: str, dist: Path | None = None
) -> FastAPI:
    # No /docs or /openapi.json: nothing is served that the pages don't need.
    app = FastAPI(title="DevAI", docs_url=None, redoc_url=None, openapi_url=None)
    prepared = Kept()
    outcomes = Kept()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = request.headers.get("host")
        if not host_allowed(host):
            response: Response = JSONResponse({"detail": "forbidden host"}, 403)
        elif request.url.path.startswith("/api/") and not token_matches(
            request.headers.get(TOKEN_HEADER), token
        ):
            response = JSONResponse({"detail": "missing or wrong token"}, 401)
        elif request.url.path.startswith("/api/") and not origin_allowed(
            request.headers.get("origin"), host
        ):
            response = JSONResponse({"detail": "forbidden origin"}, 403)
        else:
            response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    def project(pid: int) -> Project:
        if not 0 <= pid < len(projects):
            raise HTTPException(404, "no such project")
        return projects[pid]

    @app.get("/api/info")
    def info() -> dict:
        return {"version": __version__, "tasks": list(tasks.TASKS)}

    @app.get("/api/projects")
    def list_projects() -> list[dict]:
        return [{"id": p.id, "name": p.name, "path": str(p.path)} for p in projects]

    @app.get("/api/projects/{pid}/{view}")
    def view(pid: int, view: str) -> Response:
        """The deterministic reports: the same JSON as the CLI, no AI."""
        path = project(pid).path
        if view not in VIEWS:
            raise HTTPException(404, f"no such view; one of: {', '.join(VIEWS)}")
        if view == "review":
            try:
                changes = collect_changes(path)
            except ReviewError as problem:
                raise HTTPException(400, str(problem)) from None
            document = review_to_json(
                review_report(changes, run_review_checks(changes))
            )
        else:
            info = analyze_project(path)
            if view == "analysis":
                document = to_json(info, run_checks(info))
            elif view == "tests":
                document = coverage_to_json(info.name, build_coverage_map(info))
            else:
                document = docs_to_json(info.name, build_docs_map(info))
        return Response(document, media_type="application/json")

    @app.post("/api/projects/{pid}/ai")
    def prepare(pid: int, body: PrepareBody) -> dict:
        """Build what an AI task would send. Nothing is sent here."""
        try:
            settings = load_settings(provider=body.provider)
            task = tasks.prepare(
                body.task, project(pid).path, settings, body.model_dump()
            )
        except (SettingsError, tasks.TaskError) as problem:
            raise HTTPException(400, str(problem)) from None
        return {"prepared_id": prepared.put(task), **task.preview()}

    @app.post("/api/prepared/{key}/send")
    def send(key: str) -> dict:
        """The user saw the preview and clicked: send it, check the answer."""
        from devai import cli  # the same client factory the CLI (and its tests) use

        task = prepared.pop(key)
        try:
            client = cli.create_ai_client(task.settings)
            outcome = tasks.send(task, client)
        except cli.SetupError as problem:
            raise HTTPException(400, str(problem)) from None
        except AIError as problem:
            raise HTTPException(502, f"the AI {task.task} failed: {problem}") from None
        answer: dict[str, Any] = {"task": outcome.task, "result": outcome.document}
        if outcome.action is not None:
            answer["apply"] = {
                "outcome_id": outcomes.put(outcome),
                "kind": outcome.action.kind,
                "files": outcome.action.files,
                "blocked": tasks.blocked(outcome),
            }
        return answer

    @app.post("/api/outcomes/{key}/apply")
    def apply(key: str) -> dict:
        """The user saw the diff and confirmed: write it, after D044/D047 checks."""
        outcome = outcomes.pop(key)
        try:
            return {"applied": True, **tasks.apply(outcome)}
        except tasks.TaskError as problem:
            raise HTTPException(409, str(problem)) from None

    if dist is not None and (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="pages")
    else:

        @app.get("/", response_class=HTMLResponse)
        def no_pages() -> str:
            return (
                "<!doctype html><title>DevAI</title><h1>DevAI is running</h1>"
                "<p>The API works, but the pages aren't built. In a checkout, run "
                "<code>npm --prefix web ci</code> and "
                "<code>npm --prefix web run build</code>, then restart.</p>"
            )

    return app
