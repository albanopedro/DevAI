from pathlib import Path, PurePosixPath

import pytest
from conftest import FAKE_PRIVATE_KEY_HEADER, FAKE_SECRETS, make_files

from devai.analyzer import analyze_project
from devai.checks.secrets import (
    check_secrets,
    find_secrets,
    is_real_env_file,
    match_line,
)
from devai.models import Severity

# --- matching single lines ---------------------------------------------------


@pytest.mark.parametrize("rule_id", FAKE_SECRETS)
def test_detects_known_secret_formats(rule_id):
    secret, public_prefix = FAKE_SECRETS[rule_id]

    finding = match_line(f'const key = "{secret}";')

    assert finding.rule_id == rule_id
    assert finding.severity is Severity.HIGH
    assert finding.evidence == public_prefix
    assert secret not in finding.evidence


def test_detects_private_key_header():
    finding = match_line(FAKE_PRIVATE_KEY_HEADER)

    assert finding.rule_id == "secret/private-key"
    assert finding.evidence == FAKE_PRIVATE_KEY_HEADER  # header only, no key


def test_anthropic_key_is_not_also_reported_as_openai():
    secret, _ = FAKE_SECRETS["secret/anthropic-key"]

    assert match_line(secret).rule_id == "secret/anthropic-key"


@pytest.mark.parametrize(
    "line",
    [
        'className="task-management-component-v2"',  # "sk-" inside a word
        "AKIA" + "IOSFODNN7EXAMPLE",  # AWS's documented example key
        "sk-" + "abcdefghijklmnopqrstuvwxyz",  # no digits: not random-looking
        "import os",
    ],
)
def test_ignores_lookalikes_and_placeholders(line):
    assert match_line(line) is None


def test_generic_credential_assignment():
    finding = match_line('DB_PASSWORD = "s3cr3tValue"')

    assert finding.rule_id == "secret/generic"
    assert finding.severity is Severity.MEDIUM
    assert finding.evidence == "DB_PASSWORD = …"


@pytest.mark.parametrize(
    "line",
    [
        'api_key = "your-api-key"',
        'password: "changeme123"',
        'token = "<paste-token-here>"',
        'secret = "${JWT_SECRET}"',
        'password = "********"',
        'password = "short"',  # under 8 characters
        'if password == "something-long"',  # comparison, not assignment
        "api_key = os.getenv('API_KEY')",  # read from the environment
    ],
)
def test_generic_rule_ignores_placeholders_and_non_assignments(line):
    assert match_line(line) is None


def test_generic_rule_is_skipped_in_test_files():
    text = 'password = "s3cr3tValue"\n'

    assert find_secrets(text, PurePosixPath("tests/test_login.py")) == []
    assert len(find_secrets(text, PurePosixPath("src/login.py"))) == 1


def test_precise_rules_still_apply_in_test_files():
    secret, _ = FAKE_SECRETS["secret/github-token"]

    findings = find_secrets(f"TOKEN = '{secret}'\n", PurePosixPath("tests/test_a.py"))

    assert [finding.rule_id for finding in findings] == ["secret/github-token"]


def test_findings_carry_file_and_line_number():
    secret, _ = FAKE_SECRETS["secret/aws-access-key"]
    text = f"line one\nline two\nkey = '{secret}'\n"

    [finding] = find_secrets(text, PurePosixPath("src/config.ts"))

    assert (finding.file, finding.line) == (PurePosixPath("src/config.ts"), 3)


# --- which files are read ----------------------------------------------------


@pytest.mark.parametrize(
    ("name", "real"),
    [
        (".env", True),
        (".env.local", True),
        (".env.production", True),
        ("docker.env", True),
        (".envrc", True),
        (".env.example", False),
        (".env.sample", False),
        (".env.template", False),
        (".env.dist", False),
        ("environment.py", False),
    ],
)
def test_real_env_files(name, real):
    assert is_real_env_file(PurePosixPath(name)) is real


def scan(project):
    return check_secrets(analyze_project(project))


def write(root, relative, text):
    make_files(root, relative)
    (root / relative).write_text(text)


def test_scans_project_files(tmp_path):
    secret, _ = FAKE_SECRETS["secret/stripe-key"]
    write(tmp_path, "src/pay.js", f"const stripe = '{secret}';\n")
    write(tmp_path, "src/app.js", "console.log('hi');\n")

    result, stats = scan(tmp_path)

    assert [(str(f.file), f.line) for f in result.findings] == [("src/pay.js", 1)]
    assert (stats.scanned, stats.skipped) == (2, 0)


def test_clean_project_passes(tmp_path):
    write(tmp_path, "app.py", "print('hello')\n")

    result, _ = scan(tmp_path)

    assert result.findings == ()
    assert result.passed_message == "No known secret patterns found"


def test_real_env_file_is_never_opened(tmp_path, monkeypatch):
    secret, _ = FAKE_SECRETS["secret/openai-key"]
    write(tmp_path, ".env", f"OPENAI_API_KEY={secret}\n")
    write(tmp_path, "app.py", "print('hello')\n")

    opened = []
    original_read_bytes = Path.read_bytes

    def spy(self):
        opened.append(self.name)
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    result, stats = scan(tmp_path)

    assert ".env" not in opened
    assert result.findings == ()
    assert (stats.scanned, stats.skipped) == (1, 1)


def test_env_templates_are_scanned(tmp_path):
    secret, _ = FAKE_SECRETS["secret/openai-key"]
    write(tmp_path, ".env.example", f"OPENAI_API_KEY={secret}\n")

    result, _ = scan(tmp_path)

    assert [str(finding.file) for finding in result.findings] == [".env.example"]


def test_skips_lock_minified_binary_large_and_symlinked_files(tmp_path):
    secret, _ = FAKE_SECRETS["secret/aws-access-key"]
    line = f"key = '{secret}'\n"
    write(tmp_path, "package-lock.json", line)
    write(tmp_path, "dist.min.js", line)
    make_files(tmp_path, "logo.png")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\0" + line.encode())
    write(tmp_path, "big.txt", line + "x" * 1_000_001)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text(line)
    (tmp_path / "link.txt").symlink_to(outside)

    result, stats = scan(tmp_path)

    assert result.findings == ()
    assert (stats.scanned, stats.skipped) == (0, 5)
