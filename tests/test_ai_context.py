import json
from pathlib import Path, PurePosixPath

from conftest import FAKE_SECRETS, make_files

from devai.ai.context import (
    CONTEXT_VERSION,
    MAX_DEPENDENCIES_PER_MANIFEST,
    MAX_FINDINGS,
    build_context,
    estimate_tokens,
    serialize_context,
)
from devai.analyzer import analyze_project
from devai.checks import run_checks
from devai.models import (
    CheckReport,
    Dependency,
    Ecosystem,
    FileSource,
    Finding,
    Manifest,
    ProjectInfo,
    Severity,
)


def context_for(project):
    info = analyze_project(project)
    return build_context(info, run_checks(info))


def sent_text(project):
    """The context exactly as it would be sent to a model."""
    return serialize_context(context_for(project))


def write(root, relative, text):
    make_files(root, relative)
    (root / relative).write_text(text)


# --- contract: exactly these fields, nothing more ----------------------------


def test_top_level_fields_are_an_explicit_allow_list(tmp_path):
    # If this test fails, a field was added to or removed from the AI context.
    # Update it only after deciding the new field is safe to send (D025).
    assert set(context_for(tmp_path)) == {
        "context_version",
        "project",
        "languages",
        "frameworks",
        "dependencies",
        "tests",
        "config_files",
        "structure",
        "findings",
        "passed_checks",
        "secret_scan",
        "truncated",
    }


def test_project_and_finding_fields(tmp_path):
    make_files(tmp_path, ".env")

    context = context_for(tmp_path)

    assert set(context["project"]) == {"name", "file_count", "has_git", "has_readme"}
    assert set(context["findings"][0]) == {
        "rule_id",
        "severity",
        "message",
        "file",
        "line",
        "evidence",
    }
    assert context["context_version"] == CONTEXT_VERSION == 1


# --- what must never be sent -------------------------------------------------


def test_never_contains_the_absolute_path(tmp_path):
    project = tmp_path / "my-app"
    make_files(project, "src/app.py")

    text = sent_text(project)

    assert '"name":"my-app"' in text
    assert str(project.resolve()) not in text
    assert str(Path.home()) not in text


def test_never_contains_file_contents(tmp_path):
    write(tmp_path, "src/app.py", "UNIQUE_CONTENT_MARKER = 42\n")
    write(tmp_path, "README.md", "# Another UNIQUE_README_MARKER\n")

    text = sent_text(tmp_path)

    assert "UNIQUE_CONTENT_MARKER" not in text
    assert "UNIQUE_README_MARKER" not in text


def test_never_contains_env_values(tmp_path):
    write(tmp_path, ".env", "DATABASE_URL=postgres://user:hunter2@db/prod\n")

    text = sent_text(tmp_path)

    assert "hunter2" not in text
    assert "DATABASE_URL" not in text
    assert '"file":".env"' in text  # the exposed file is reported by name only


def test_secrets_appear_only_masked(tmp_path):
    secret, public_prefix = FAKE_SECRETS["secret/aws-access-key"]
    write(tmp_path, "src/config.ts", f"export const key = '{secret}';\n")

    text = sent_text(tmp_path)

    assert secret not in text
    assert secret[len("AKIA") :] not in text
    assert f'"evidence":"{public_prefix}"' in text


def test_individual_file_names_are_not_sent(tmp_path):
    make_files(tmp_path, "src/very_private_notes.py", "src/app.py")

    text = sent_text(tmp_path)

    assert "very_private_notes" not in text
    assert '"name":"src"' in text  # only the top-level directory and its count


def test_dependency_versions_are_not_sent(tmp_path):
    write(
        tmp_path,
        "package.json",
        '{"dependencies": {"react": "^19.1.0"}, "devDependencies": {"vite": "7.0.2"}}',
    )

    [manifest] = context_for(tmp_path)["dependencies"]

    assert manifest["runtime"] == ["react"]
    assert manifest["dev"] == ["vite"]
    assert "19.1.0" not in sent_text(tmp_path)


# --- size limits -------------------------------------------------------------


def minimal_info(**fields):
    defaults = dict(
        name="big",
        path=Path("/unused"),
        file_count=0,
        file_source=FileSource.FILESYSTEM,
        has_git=False,
        has_readme=True,
    )
    return ProjectInfo(**(defaults | fields))


def test_long_lists_are_truncated_and_flagged():
    findings = tuple(
        Finding("secret/generic", Severity.MEDIUM, "Possible hardcoded credential")
        for _ in range(MAX_FINDINGS + 10)
    )
    dependencies = tuple(
        Dependency(f"pkg-{number}")
        for number in range(MAX_DEPENDENCIES_PER_MANIFEST + 5)
    )
    manifest = Manifest(PurePosixPath("package.json"), Ecosystem.NPM, dependencies)

    context = build_context(
        minimal_info(manifests=(manifest,)), CheckReport(findings=findings)
    )

    assert len(context["findings"]) == MAX_FINDINGS
    assert len(context["dependencies"][0]["runtime"]) == MAX_DEPENDENCIES_PER_MANIFEST
    assert context["truncated"] == {
        "findings": {"shown": MAX_FINDINGS, "total": MAX_FINDINGS + 10},
        "dependencies:package.json": {
            "shown": MAX_DEPENDENCIES_PER_MANIFEST,
            "total": MAX_DEPENDENCIES_PER_MANIFEST + 5,
        },
    }


def test_small_project_is_not_truncated(tmp_path):
    make_files(tmp_path, "app.py")

    assert context_for(tmp_path)["truncated"] == {}


# --- serialization -----------------------------------------------------------


def test_context_is_deterministic_and_compact(tmp_path):
    make_files(tmp_path, "src/app.py", "README.md")

    first, second = sent_text(tmp_path), sent_text(tmp_path)

    assert first == second  # stable input matters for caching later
    assert "\n" not in first and ": " not in first
    assert json.loads(first)["project"]["file_count"] == 2


def test_estimate_tokens_rounds_up():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcde") == 2
