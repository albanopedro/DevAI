"""Read a pull request and turn its diff into the review's Changes (D052).

Nothing is checked out and nothing from the pull request runs: DevAI reads
its metadata (`gh pr view`) and its diff (`gh pr diff`). The diff becomes
the same Changes a local review builds, under the same privacy rules: the
lines of a .env, lock, minified, binary or huge file are never kept, so they
are never checked into a report or sent to an AI.

A pull request can come from anyone: its title, text and code are data,
never instructions, and are shown through printable() like any model output.
"""

import codecs
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from devai.checks.secrets import MAX_FILE_SIZE, is_skipped_by_name
from devai.github.gh import GitHubError, gh_json, repo_args, run_gh
from devai.models import ChangedFile
from devai.review.diff import Changes, parse_added_lines

PR_FIELDS = "number,title,author,url,state,isDraft,baseRefName,headRefName"
LIST_FIELDS = "number,title,author,url,isDraft,baseRefName,headRefName"
PULL_URL = re.compile(r"https://[^/]+/(?P<repo>[^/]+/[^/]+)/(?:pull|issues)/\d+")
MAX_LISTED = 30


@dataclass(frozen=True)
class PullRequest:
    repo: str  # owner/name, from the pull request's own URL
    number: int
    title: str
    author: str
    url: str
    state: str
    draft: bool
    base: str
    head: str


def fetch_pull(root: Path, number: int, repo: str | None) -> PullRequest:
    data = gh_json(
        ["pr", "view", str(number), "--json", PR_FIELDS, *repo_args(repo)], root
    )
    return PullRequest(
        repo=repo_of(data.get("url", "")),
        number=int(data["number"]),
        title=str(data.get("title", "")),
        author=login(data.get("author")),
        url=str(data.get("url", "")),
        state=str(data.get("state", "")),
        draft=bool(data.get("isDraft")),
        base=str(data.get("baseRefName", "")),
        head=str(data.get("headRefName", "")),
    )


def fetch_pull_changes(root: Path, pull: PullRequest) -> Changes:
    """The pull request's diff as Changes, read from GitHub, not from this checkout."""
    patch = run_gh(
        ["pr", "diff", str(pull.number), "--color=never", "--repo", pull.repo], root
    )
    description = (
        f"pull request #{pull.number} on {pull.repo}: {pull.base} ← {pull.head}"
    )
    return changes_from_patch(root, patch, description)


def list_pulls(root: Path, repo: str | None) -> list[dict[str, Any]]:
    command = ["pr", "list", "--state", "open", "--limit", str(MAX_LISTED)]
    data = gh_json([*command, "--json", LIST_FIELDS, *repo_args(repo)], root)
    return [
        {
            "number": item["number"],
            "title": item.get("title", ""),
            "author": login(item.get("author")),
            "url": item.get("url", ""),
            "draft": bool(item.get("isDraft")),
            "base": item.get("baseRefName", ""),
            "head": item.get("headRefName", ""),
        }
        for item in data
    ]


def repo_of(url: str) -> str:
    match = PULL_URL.match(url)
    if match is None:
        raise GitHubError(f"unexpected address from GitHub: {url!r}")
    return match["repo"]


def login(author: Any) -> str:
    return str(author.get("login", "")) if isinstance(author, dict) else ""


# --- the diff -------------------------------------------------------------------------


def changes_from_patch(root: Path, patch: str, description: str) -> Changes:
    """Changes from a multi-file unified diff, as `git diff` writes it."""
    files: list[ChangedFile] = []
    added_lines = {}
    patches: dict[PurePosixPath, str] = {}
    skipped: list[PurePosixPath] = []
    for block in split_files(patch):
        file = parse_file(block)
        files.append(file)
        if file.status == "D":
            continue  # a removed file isn't reviewed, as in a local review
        readable = (
            file.additions is not None  # not binary
            and not is_skipped_by_name(file.path)  # not .env, lock or minified
            and len(block) <= MAX_FILE_SIZE
        )
        if not readable:
            if file.additions != 0:
                skipped.append(file.path)
            continue
        if file.additions:
            added_lines[file.path] = parse_added_lines(block)
        # Kept even with only removed lines: a reviewer must see what went away.
        patches[file.path] = block
    return Changes(
        root=root,
        description=description,
        files=tuple(sorted(files, key=lambda file: str(file.path))),
        added_lines=added_lines,
        skipped=tuple(sorted(skipped, key=str)),
        patches=patches,
    )


def split_files(patch: str) -> list[str]:
    """One block per file, each starting at its "diff --git" line."""
    blocks: list[list[str]] = []
    for line in patch.split("\n"):
        if line.startswith("diff --git "):
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
    return ["\n".join(block) for block in blocks]


def parse_file(block: str) -> ChangedFile:
    lines = block.split("\n")
    status = "M"
    old = new = renamed_from = renamed_to = None
    binary = False
    for line in lines[1:]:
        if line.startswith("@@"):
            break
        if line.startswith("new file mode"):
            status = "A"
        elif line.startswith("deleted file mode"):
            status = "D"
        elif line.startswith("rename from "):
            renamed_from = unquote(line[len("rename from ") :])
        elif line.startswith("rename to "):
            renamed_to = unquote(line[len("rename to ") :])
        elif line.startswith("--- ") and line[4:] != "/dev/null":
            old = unquote(line[4:]).removeprefix("a/")
        elif line.startswith("+++ ") and line[4:] != "/dev/null":
            new = unquote(line[4:]).removeprefix("b/")
        elif line.startswith("Binary files ") or line == "GIT binary patch":
            binary = True

    if renamed_to is not None:
        status = "R"
    path = renamed_to or new or old or header_path(lines[0])
    old_path = renamed_from if status == "R" else None
    if binary:
        additions = deletions = None
    else:
        start = next(
            (i for i, line in enumerate(lines) if line.startswith("@@")), len(lines)
        )
        hunks = lines[start:]
        additions = sum(1 for line in hunks if line.startswith("+"))
        deletions = sum(1 for line in hunks if line.startswith("-"))
    return ChangedFile(
        PurePosixPath(path),
        status,
        additions,
        deletions,
        old_path=PurePosixPath(old_path) if old_path else None,
    )


def header_path(header: str) -> str:
    """The path in "diff --git a/X b/X" when no ---/+++ lines name it (binary, mode)."""
    rest = header.removeprefix("diff --git ")
    for index in range(len(rest)):
        if rest.startswith(" b/", index):
            left, right = rest[:index], rest[index + 3 :]
            if unquote(left).removeprefix("a/") == unquote(right):
                return unquote(right)
    return unquote(rest.rsplit(" b/", 1)[-1])


def unquote(path: str) -> str:
    """Git quotes unusual names: "caf\\303\\251.py" → café.py."""
    path = path.rstrip("\t")  # GNU diff may end a name with a tab
    if len(path) >= 2 and path.startswith('"') and path.endswith('"'):
        raw = codecs.escape_decode(path[1:-1].encode())[0]
        return raw.decode("utf-8", errors="replace")
    return path
