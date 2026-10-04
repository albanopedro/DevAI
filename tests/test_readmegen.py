import json
import re
from pathlib import PurePosixPath

import pytest
from conftest import FAKE_SECRETS, write

from devai.analyzer import analyze_project
from devai.docmap.readme import readme_map
from devai.models import CheckReport
from devai.readmegen import plan as plan_module
from devai.readmegen.context import (
    MAX_README_LINES,
    README_CONTEXT_VERSION,
    ProjectFacts,
    build_readme_context,
    project_facts,
    readme_topics,
)
from devai.readmegen.plan import ReadmeError, plan_readme, section_level

README = PurePosixPath("README.md")
NODE = ProjectFacts(frozenset({"dev", "test"}), has_package_json=True, has_python=False)
ASKED = ["installation", "usage", "tests"]
INSTALL = ("installation", "Installation", "```bash\nnpm install\n```")
USAGE = ("usage", "Usage", "Run `npm run dev`.")


@pytest.fixture
def node_project(tmp_path):
    write(tmp_path, "package.json", '{"scripts": {"dev": "vite", "test": "vitest"}}')
    return tmp_path


def plan(root, before, sections, facts=NODE, description="", asked=ASKED):
    files = tuple(
        PurePosixPath(p.relative_to(root).as_posix())
        for p in sorted(root.rglob("*"))
        if p.is_file()
    )
    return plan_readme(
        README, before, sections, description, asked, "demo", facts, root, files
    )


# --- which topics are asked -----------------------------------------------------------


def test_license_is_never_asked_and_tests_only_with_tests(tmp_path):
    write(tmp_path, "app.py", "x = 1\n")
    info = analyze_project(tmp_path)

    asked, left_out = readme_topics(info, None)

    assert asked == ["installation", "usage"]
    assert left_out == [
        ("tests", "the project has no tests to describe"),
        ("license", "choosing a license is your decision: add a LICENSE file"),
    ]


def test_only_missing_topics_are_asked(tmp_path):
    write(tmp_path, "README.md", "# Demo\n\n## Usage\n")
    write(tmp_path, "tests/test_app.py", "def test_ok():\n    pass\n")
    write(tmp_path, "LICENSE", "MIT\n")
    info = analyze_project(tmp_path)
    readme = readme_map(README, "# Demo\n\n## Usage\n", tmp_path, info.files)

    assert readme_topics(info, readme) == (["installation", "tests"], [])


def test_project_facts(tmp_path):
    write(tmp_path, "web/package.json", '{"scripts": {"build": "vite build"}}')
    write(tmp_path, "pyproject.toml", "[project]\nname = 'x'\n")

    facts = project_facts(analyze_project(tmp_path))

    assert facts == ProjectFacts(frozenset({"build"}), True, True)


# --- context --------------------------------------------------------------------------


def test_context_fields_are_an_explicit_allow_list(tmp_path):
    # If this fails, what a README proposal receives changed: decide it's safe (D050).
    write(tmp_path, "package.json", '{"scripts": {"dev": "vite"}}')
    write(
        tmp_path,
        "pyproject.toml",
        "[project]\nname = 'x'\n\n[project.scripts]\ndemo = 'demo.cli:main'\n",
    )
    write(tmp_path, "src/demo/cli.py", "SOURCE_CODE_IS_NEVER_SENT = 1\n")
    info = analyze_project(tmp_path)

    context = build_readme_context(
        info, CheckReport(), README, "# Demo\n", ["installation"]
    )

    assert set(context) == {
        "readme_context_version",
        "project",
        "readme",
        "topics",
        "scripts",
        "redacted_lines",
        "truncated",
    }
    assert context["readme_context_version"] == README_CONTEXT_VERSION == 1
    assert context["readme"] == {
        "path": "README.md",
        "exists": True,
        "content": "# Demo\n",
    }
    assert context["scripts"] == {
        "package.json": {
            "run_with": "npm run <name> (npm test and npm start for those two)",
            "scripts": {"dev": "vite"},
        },
        "pyproject.toml": {
            "run_with": "<name>: a command, available after installing the package",
            "scripts": {"demo": "demo.cli:main"},
        },
    }
    assert "SOURCE_CODE_IS_NEVER_SENT" not in json.dumps(context)
    assert str(tmp_path) not in json.dumps(context)


def test_scripts_in_a_folder_say_where_they_run(tmp_path):
    write(tmp_path, "web/package.json", '{"scripts": {"dev": "vite"}}')
    info = analyze_project(tmp_path)

    context = build_readme_context(info, CheckReport(), None, None, ["usage"])

    assert context["scripts"]["web/package.json"]["run_with"].endswith(", from web/")


def test_context_redacts_the_readme_and_the_scripts(tmp_path):
    secret, _ = FAKE_SECRETS["secret/github-token"]
    write(tmp_path, "package.json", json.dumps({"scripts": {"x": f"TOKEN={secret} y"}}))
    info = analyze_project(tmp_path)

    context = build_readme_context(
        info, CheckReport(), README, f"Token: {secret}\n", ["usage"]
    )

    assert secret not in json.dumps(context)
    assert context["redacted_lines"] == 2


def test_context_without_a_readme_and_a_long_readme(tmp_path):
    info = analyze_project(tmp_path)

    empty = build_readme_context(info, CheckReport(), None, None, ["usage"])
    long = build_readme_context(info, CheckReport(), README, "x\n" * 500, ["usage"])

    assert empty["readme"] == {"path": None, "exists": False, "content": ""}
    assert long["truncated"]["readme"] == {"shown": MAX_README_LINES, "total": 501}


# --- where sections go ----------------------------------------------------------------


def test_sections_go_before_the_license_section(node_project):
    before = "# Demo\n\nA demo.\n\n## License\n\nMIT\n"

    result = plan(node_project, before, [USAGE, INSTALL])

    assert result.change.after == (
        "# Demo\n"
        "\n"
        "A demo.\n"
        "\n"
        "## Installation\n"  # in topic order, whatever order the AI used
        "\n"
        "```bash\n"
        "npm install\n"
        "```\n"
        "\n"
        "## Usage\n"
        "\n"
        "Run `npm run dev`.\n"
        "\n"
        "## License\n"
        "\n"
        "MIT\n"
    )
    assert result.added == (("installation", "Installation"), ("usage", "Usage"))
    assert result.creates is False


def test_sections_go_at_the_end_without_a_license_section(node_project):
    result = plan(node_project, "# Demo\n\nNo final newline.", [USAGE])

    assert result.change.after == (
        "# Demo\n\nNo final newline.\n\n## Usage\n\nRun `npm run dev`.\n"
    )


def test_crlf_readmes_stay_crlf(node_project):
    result = plan(node_project, "# Demo\r\n\r\n## License\r\n", [USAGE])

    assert "## Usage\r\n\r\nRun `npm run dev`.\r\n\r\n## License\r\n" in (
        result.change.after
    )
    assert "\n" not in result.change.after.replace("\r\n", "")


def test_a_title_naming_a_license_is_not_the_license_section(node_project):
    result = plan(node_project, "# MIT License Checker\n\nA tool.\n", [USAGE])

    assert result.change.after.endswith("A tool.\n\n## Usage\n\nRun `npm run dev`.\n")


def test_sections_use_the_readmes_own_level(node_project):
    before = "# Demo\n\n### About\n\n### More\n\n## Odd one\n"

    assert section_level(before) == 3
    assert "\n### Usage\n" in plan(node_project, before, [USAGE]).change.after
    assert section_level("# Only a title\n") == 2


# --- sections dropped, with the reason ------------------------------------------------


@pytest.mark.parametrize(
    ("section", "why"),
    [
        (("license", "License", "MIT"), "not one of the topics DevAI asked for"),
        (("usage", "", "Run it."), "no heading"),
        (("usage", "Overview", "Run it."), "the heading doesn't name the usage"),
        (("usage", "Usage\nMore", "Run it."), "the heading has several lines"),
        (("usage", "Usage", "  \n "), "no text"),
        (("usage", "Usage", "line\n" * 41), "too long (at most 40 lines)"),
        (("usage", "Usage", "## Details\n\nx"), "headings at the section's own level"),
        (("usage", "Usage", "```bash\nnpm run dev\n"), "a code block isn't closed"),
        (("usage", "Usage", "`npm run deploy`"), "runs a script no package.json has"),
    ],
)
def test_sections_that_are_dropped(node_project, section, why):
    result = plan(node_project, "# Demo\n", [section])

    assert result.change is None
    assert len(result.dropped) == 1
    assert why in result.dropped[0][1]


def test_a_second_section_for_a_topic_is_dropped(node_project):
    result = plan(node_project, "# Demo\n", [USAGE, ("usage", "Usage", "Again.")])

    assert result.added == (("usage", "Usage"),)
    assert result.dropped == (("usage (Usage)", "a second section for the same topic"),)


def test_deeper_headings_inside_a_section_are_fine(node_project):
    result = plan(node_project, "# Demo\n", [("usage", "Usage", "### Dev\n\nRun it.")])

    assert result.added == (("usage", "Usage"),)


@pytest.mark.parametrize(
    ("command", "facts", "why"),
    [
        ("npm install", ProjectFacts(frozenset(), False, True), "uses npm, but"),
        ("yarn build", ProjectFacts(frozenset(), False, True), "uses yarn, but"),
        ("pip install -e .", ProjectFacts(frozenset(), True, False), "uses pip, but"),
        ("pytest", ProjectFacts(frozenset(), True, False), "uses pytest, but"),
        ("npm run dev", ProjectFacts(None, True, False), "can't be checked"),
    ],
)
def test_commands_that_cant_work_here(tmp_path, command, facts, why):
    section = ("usage", "Usage", f"```bash\n{command}\n```")

    result = plan(tmp_path, "# Demo\n", [section], facts=facts)

    assert why in result.dropped[0][1]


@pytest.mark.parametrize(
    "command",
    [
        "python3 -m http.server",  # serves any static site
        "npx serve .",
        "npm install -g serve",
    ],
)
def test_commands_any_project_can_run(tmp_path, command):
    facts = ProjectFacts(frozenset(), has_package_json=False, has_python=False)
    section = ("usage", "Usage", f"```bash\n{command}\n```")

    assert plan(tmp_path, "# Demo\n", [section], facts=facts).added


def test_links_are_listed_for_the_user_to_check(node_project):
    body = "See https://example.com/docs. Or https://example.com/docs, again."

    result = plan(node_project, "# Demo\n", [("usage", "Usage", body)])

    assert result.links == ("https://example.com/docs",)


# --- unsafe text rejects everything ---------------------------------------------------


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("Uses [redacted: possible secret] here.", "hidden as a possible secret"),
        ("Token: " + FAKE_SECRETS["secret/github-token"][0], "possible secret"),
        ('<script>alert("x")</script>', "HTML that runs code"),
        ("[Open](javascript:alert(1))", "HTML that runs code"),
    ],
)
def test_unsafe_text_rejects_the_whole_proposal(node_project, body, reason):
    with pytest.raises(ReadmeError, match=re.escape(reason)):
        plan(node_project, "# Demo\n", [INSTALL, ("usage", "Usage", body)])


# --- a new README ---------------------------------------------------------------------


def test_a_new_readme(node_project):
    result = plan(node_project, None, [INSTALL], description="A demo project.")

    assert result.creates is True
    assert result.change.before == ""
    assert result.change.after == (
        "# demo\n\nA demo project.\n\n## Installation\n\n```bash\nnpm install\n```\n"
    )


def test_a_description_that_is_not_plain_sentences_is_dropped(node_project):
    result = plan(node_project, None, [INSTALL], description="## Title\n\nText.")

    assert result.change.after.startswith("# demo\n\n## Installation\n")
    why = "it should be plain sentences, without headings or code blocks"
    assert result.dropped == (("description", why),)


def test_inline_code_in_a_description_is_fine(node_project):
    result = plan(node_project, None, [INSTALL], description="Run it as `demo`.")

    assert result.change.after.startswith("# demo\n\nRun it as `demo`.\n")
    assert result.dropped == ()


# --- the checks on the result catch a placement bug -----------------------------------


def test_a_change_to_the_readmes_own_lines_is_rejected(node_project, monkeypatch):
    real = plan_module.add_sections

    def rewrites_the_title(before, sections, level):
        after, start, block = real(before, sections, level)
        return after.replace("# Demo", "# Changed"), start, block

    monkeypatch.setattr(plan_module, "add_sections", rewrites_the_title)

    with pytest.raises(ReadmeError, match="own lines would change"):
        plan(node_project, "# Demo\n", [USAGE])


def test_a_section_devai_docs_wouldnt_find_is_rejected(node_project, monkeypatch):
    monkeypatch.setattr(
        plan_module,
        "section_lines",
        lambda section, level: ["```", "## " + section.heading, "```", ""],
    )

    with pytest.raises(ReadmeError, match="wouldn't find the usage section"):
        plan(node_project, "# Demo\n", [USAGE])


def test_a_command_that_fails_on_disk_is_rejected(node_project):
    # The facts claim a "deploy" script; the package.json on disk has none.
    facts = ProjectFacts(frozenset({"dev", "test", "deploy"}), True, False)
    section = ("usage", "Usage", "`npm run deploy`")

    with pytest.raises(ReadmeError, match="npm run deploy, which fails"):
        plan(node_project, "# Demo\n", [section], facts=facts)


def test_commands_that_already_failed_dont_block_new_sections(node_project):
    before = "# Demo\n\n`npm run old-script`\n"

    result = plan(node_project, before, [USAGE])

    assert result.added == (("usage", "Usage"),)
