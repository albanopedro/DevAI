"""Run the GitHub CLI for DevAI: only the commands DevAI needs (D052).

DevAI never sees a token: `gh auth login` keeps the login in the system's
keychain, and gh signs every request. ALLOWED lists every gh command DevAI
may run. Anything else, such as `gh pr merge`, `gh pr create`, `gh pr review`
or a `gh api` call that writes, is refused here, before any process starts.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

ALLOWED = frozenset(
    {
        ("pr", "view"),
        ("pr", "diff"),
        ("pr", "list"),
        ("pr", "comment"),  # only after the user's "y" (comment.py)
        ("issue", "view"),
        ("issue", "list"),
        ("issue", "comment"),  # only after the user's "y" (comment.py)
        ("repo", "view"),
        ("api", "user"),  # the account name, shown before posting
    }
)
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_.-]+")
TIMEOUT = 60  # seconds
INSTALL_HINT = (
    "the GitHub CLI (gh) isn't installed. It's free: https://cli.github.com, "
    "then run `gh auth login`"
)


class GitHubError(Exception):
    """gh couldn't do it. The message is safe to show."""


def run_gh(args: list[str], cwd: Path, stdin: str | None = None) -> str:
    """Run `gh *args` in `cwd` and return its output. No shell, no prompts."""
    if tuple(args[:2]) not in ALLOWED:
        raise GitHubError(f"DevAI doesn't run `gh {' '.join(args[:2])}`")
    environment = {
        **os.environ,
        "GH_PROMPT_DISABLED": "1",  # never wait for an answer in a terminal
        "GH_NO_UPDATE_NOTIFIER": "1",
        "GH_PAGER": "cat",
        "NO_COLOR": "1",
    }
    try:
        result = subprocess.run(
            ["gh", *args],
            cwd=cwd,
            input=stdin,
            capture_output=True,
            text=True,
            env=environment,
            timeout=TIMEOUT,
        )
    except FileNotFoundError:
        raise GitHubError(INSTALL_HINT) from None
    except subprocess.TimeoutExpired:
        raise GitHubError(f"GitHub didn't answer in {TIMEOUT} seconds") from None
    if result.returncode != 0:
        raise GitHubError(explain(result.stderr))
    return result.stdout


def gh_json(args: list[str], cwd: Path) -> Any:
    output = run_gh(args, cwd)
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        raise GitHubError("gh answered something DevAI can't read") from None


def explain(stderr: str) -> str:
    """gh's error, shortened, with the fix when DevAI knows it."""
    text = " ".join(stderr.split())
    lowered = text.lower()
    if "gh auth login" in lowered or "not logged" in lowered:
        return "gh isn't logged in to GitHub: run `gh auth login`"
    if "not a git repository" in lowered or "no git remotes" in lowered:
        return (
            "this folder has no GitHub repository "
            "(in the terminal, name one with --repo owner/name)"
        )
    return text[:300] or "gh failed without a message"


def repo_args(repo: str | None) -> list[str]:
    """["--repo", repo], after checking it can't be read as an option."""
    if repo is None:
        return []
    if not REPO.fullmatch(repo):
        raise GitHubError(f"{repo!r} isn't a repository name like owner/name")
    return ["--repo", repo]


def current_account(cwd: Path) -> str:
    """The login gh posts as: shown before anything is posted."""
    return run_gh(["api", "user", "--jq", ".login"], cwd).strip()


def local_repo(cwd: Path) -> str | None:
    """The GitHub repository of this checkout (owner/name), or None."""
    try:
        data = gh_json(["repo", "view", "--json", "nameWithOwner"], cwd)
    except GitHubError:
        return None
    return data.get("nameWithOwner") if isinstance(data, dict) else None
