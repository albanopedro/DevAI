"""Scan project files for hardcoded secrets.

Privacy rules (D021):
- Real .env files are never opened. Templates such as .env.example are
  scanned, because they are meant to be committed.
- Symlinks, lock files, minified files, binaries and files over 1 MB are
  skipped.
- A finding shows only the public prefix of a secret (e.g. "AKIA…"), which
  is the same for everyone. Never the secret itself, never the line.
- File contents are checked in memory and discarded. Nothing is sent anywhere.
"""

import re
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from devai.analyzer.testing import is_test_file
from devai.checks.result import CheckResult, failing, passing
from devai.models import Finding, ProjectInfo, SecretScanStats, Severity

MAX_FILE_SIZE = 1_000_000  # bytes
BINARY_SNIFF_SIZE = 8192  # a NUL byte among the first bytes means binary

LOCK_FILES = frozenset(
    {
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "bun.lock",
        "bun.lockb",
        "poetry.lock",
        "uv.lock",
        "pipfile.lock",
        "cargo.lock",
        "composer.lock",
        "gemfile.lock",
        "go.sum",
    }
)
MINIFIED_SUFFIXES = (".min.js", ".min.css", ".map")
ENV_TEMPLATE_HINTS = ("example", "sample", "template", "dist")


@dataclass(frozen=True)
class SecretRule:
    rule_id: str
    message: str
    pattern: re.Pattern[str]  # group "prefix" = public part shown as evidence


# A token must not continue a longer word: "task-manager..." never matches "sk-".
_START = r"(?<![A-Za-z0-9_-])"

# Most specific first: the first rule that matches a line wins.
SECRET_RULES = (
    SecretRule(
        "secret/aws-access-key",
        "Possible AWS access key",
        re.compile(_START + r"(?P<prefix>AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])"),
    ),
    SecretRule(
        "secret/github-token",
        "Possible GitHub token",
        re.compile(_START + r"(?P<prefix>gh[pousr]_|github_pat_)[A-Za-z0-9_]{22,}"),
    ),
    SecretRule(
        "secret/anthropic-key",
        "Possible Anthropic API key",
        re.compile(_START + r"(?P<prefix>sk-ant-)[A-Za-z0-9_-]{20,}"),
    ),
    SecretRule(
        "secret/openai-key",
        "Possible OpenAI API key",
        re.compile(_START + r"(?P<prefix>sk-(?!ant-)(?:proj-)?)[A-Za-z0-9_-]{20,}"),
    ),
    SecretRule(
        "secret/google-api-key",
        "Possible Google API key",
        re.compile(_START + r"(?P<prefix>AIza)[0-9A-Za-z_-]{35}"),
    ),
    SecretRule(
        "secret/slack-token",
        "Possible Slack token",
        re.compile(_START + r"(?P<prefix>xox[abposr]-)[A-Za-z0-9-]{10,}"),
    ),
    SecretRule(
        "secret/stripe-key",
        "Possible Stripe live key",
        re.compile(_START + r"(?P<prefix>[rs]k_live_)[0-9A-Za-z]{24,}"),
    ),
    SecretRule(
        "secret/private-key",
        "Private key",
        re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    ),
)

# api_key = "...", DB_PASSWORD: '...', "secret": "..." (value quoted, 8+ chars).
GENERIC_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(?P<key>[A-Za-z0-9_]*?"
    r"(?:api[_-]?key|secret(?:[_-]?key)?|(?:access|auth)[_-]?token|token"
    r"|passw(?:or)?d|pwd))"
    r"[\"']?\s*[:=]\s*[\"'](?P<value>[^\"'\s]{8,})[\"']"
)
PLACEHOLDER = re.compile(
    r"(?i)example|sample|dummy|placeholder|changeme|change[_-]me|your[_-]|xxx"
    r"|redacted|\*{3}|<[^>]*>|\$\{|\{\{|%\("
)


def check_secrets(info: ProjectInfo) -> tuple[CheckResult, SecretScanStats]:
    findings = []
    scanned = skipped = 0
    for path in info.files:
        text = read_scannable_text(info.path / path, path)
        if text is None:
            skipped += 1
            continue
        scanned += 1
        findings.extend(find_secrets(text, path))

    stats = SecretScanStats(scanned, skipped)
    if findings:
        return failing(*findings), stats
    return passing("No known secret patterns found"), stats


def read_scannable_text(file: Path, path: PurePosixPath) -> str | None:
    """Return the text of `file`, or None if the rules above skip it."""
    if is_skipped_by_name(path):
        return None  # decided by name alone: the file is never opened
    try:
        if file.is_symlink() or file.stat().st_size > MAX_FILE_SIZE:
            return None
        data = file.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:BINARY_SNIFF_SIZE]:
        return None
    return data.decode("utf-8", errors="replace")


def is_skipped_by_name(path: PurePosixPath) -> bool:
    name = path.name.lower()
    return (
        is_real_env_file(path) or name in LOCK_FILES or name.endswith(MINIFIED_SUFFIXES)
    )


def is_real_env_file(path: PurePosixPath) -> bool:
    """A .env-style file that may hold real values (not .env.example etc.)."""
    name = path.name.lower()
    is_env = (
        name in {".env", ".envrc"} or name.startswith(".env.") or name.endswith(".env")
    )
    return is_env and not any(hint in name for hint in ENV_TEMPLATE_HINTS)


def find_secrets(text: str, path: PurePosixPath) -> list[Finding]:
    # Tests are full of fake passwords; only the precise rules apply there.
    include_generic = not is_test_file(path)
    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        finding = match_line(line, include_generic)
        if finding is not None:
            findings.append(replace(finding, file=path, line=number))
    return findings


def match_line(line: str, include_generic: bool = True) -> Finding | None:
    """Return the first secret found in `line` (file and line not set)."""
    for rule in SECRET_RULES:
        for match in rule.pattern.finditer(line):
            if is_plausible(match):
                return Finding(
                    rule.rule_id,
                    Severity.HIGH,
                    rule.message,
                    evidence=public_part(match),
                )

    if include_generic:
        for match in GENERIC_ASSIGNMENT.finditer(line):
            if not PLACEHOLDER.search(match["value"]):
                return Finding(
                    "secret/generic",
                    Severity.MEDIUM,
                    "Possible hardcoded credential",
                    evidence=f"{match['key']} = …",
                )
    return None


def is_plausible(match: re.Match[str]) -> bool:
    """Reject placeholders and values that don't look randomly generated."""
    value = match.group()
    if PLACEHOLDER.search(value):
        return False
    prefix = match.groupdict().get("prefix")
    if prefix is None:
        return True  # a private key header is always worth reporting
    random_part = value[len(prefix) :]
    return any(char.isdigit() for char in random_part) and any(
        char.isalpha() for char in random_part
    )


def public_part(match: re.Match[str]) -> str:
    """Evidence that reveals nothing secret: the prefix everyone's token shares."""
    prefix = match.groupdict().get("prefix")
    return f"{prefix}…" if prefix else match.group()


def redact_line(text: str) -> tuple[str, bool]:
    """Replace `text` whole if it may contain a secret, before it leaves the machine.

    Stricter than detection: the generic credential rule applies everywhere,
    test files included. Hiding a line costs a little context; a sent secret
    can't be recalled (D036, D039).
    """
    finding = match_line(text, include_generic=True)
    if finding is None:
        return text, False
    return f"[redacted: possible secret ({finding.evidence})]", True
