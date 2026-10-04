"""Read GitHub issues (D054). Their text comes from anyone: it is data, shown
through printable() and redacted before an AI sees it."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devai.github.gh import gh_json, repo_args
from devai.github.pulls import login, repo_of

ISSUE_FIELDS = "number,title,author,url,state,labels,body,comments"
LIST_FIELDS = "number,title,author,url,labels,createdAt"
MAX_LISTED = 30
MAX_COMMENTS = 5  # the latest ones


@dataclass(frozen=True)
class Issue:
    repo: str
    number: int
    title: str
    author: str
    url: str
    state: str
    labels: tuple[str, ...]
    body: str
    comments: tuple[tuple[str, str], ...]  # (author, text), the latest MAX_COMMENTS
    total_comments: int


def fetch_issue(root: Path, number: int, repo: str | None) -> Issue:
    data = gh_json(
        ["issue", "view", str(number), "--json", ISSUE_FIELDS, *repo_args(repo)], root
    )
    comments = data.get("comments") or []
    return Issue(
        repo=repo_of(data.get("url", "")),
        number=int(data["number"]),
        title=str(data.get("title", "")),
        author=login(data.get("author")),
        url=str(data.get("url", "")),
        state=str(data.get("state", "")),
        labels=tuple(labels(data.get("labels"))),
        body=str(data.get("body") or ""),
        comments=tuple(
            (login(comment.get("author")), str(comment.get("body") or ""))
            for comment in comments[-MAX_COMMENTS:]
        ),
        total_comments=len(comments),
    )


def list_issues(root: Path, repo: str | None) -> list[dict[str, Any]]:
    command = ["issue", "list", "--state", "open", "--limit", str(MAX_LISTED)]
    data = gh_json([*command, "--json", LIST_FIELDS, *repo_args(repo)], root)
    return [
        {
            "number": item["number"],
            "title": item.get("title", ""),
            "author": login(item.get("author")),
            "url": item.get("url", ""),
            "labels": labels(item.get("labels")),
            "created": item.get("createdAt", ""),
        }
        for item in data
    ]


def labels(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item.get("name", "")) for item in items if isinstance(item, dict)]
