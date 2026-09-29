import json
from pathlib import PurePosixPath

import pytest
from conftest import make_files

from devai.analyzer.dependencies import (
    detect_manifests,
    parse_package_json,
    parse_pyproject,
    parse_requirements,
    python_name,
)
from devai.models import Dependency, Ecosystem, Manifest


def write(root, relative, text):
    make_files(root, relative)
    (root / relative).write_text(text)


def detect(root, *relative_paths):
    return detect_manifests(root, [PurePosixPath(p) for p in relative_paths])


# --- package.json ------------------------------------------------------------


def test_package_json_runtime_and_dev_dependencies():
    text = json.dumps(
        {
            "name": "app",
            "dependencies": {"react": "^19.0.0", "@angular/core": "17"},
            "devDependencies": {"vite": "^6.0.0"},
        }
    )

    assert parse_package_json(text) == [
        Dependency("react"),
        Dependency("@angular/core"),
        Dependency("vite", dev=True),
    ]


def test_package_json_without_dependencies():
    assert parse_package_json('{"name": "empty"}') == []


@pytest.mark.parametrize("text", ["[]", '{"dependencies": ["react"]}'])
def test_package_json_with_wrong_shape_is_rejected(text):
    with pytest.raises(ValueError):
        parse_package_json(text)


# --- pyproject.toml ----------------------------------------------------------


def test_pyproject_dependencies_and_groups():
    text = """
[project]
name = "app"
dependencies = [
    "FastAPI[standard]>=0.110",
    "typing_extensions; python_version < '3.12'",
]

[project.optional-dependencies]
dev = ["pytest>=8"]
postgres = ["psycopg"]

[dependency-groups]
lint = ["ruff"]
"""

    assert parse_pyproject(text) == [
        Dependency("fastapi"),
        Dependency("typing-extensions"),
        Dependency("pytest", dev=True),
        Dependency("psycopg"),  # a non-dev extra is a runtime option
        Dependency("ruff", dev=True),
    ]


def test_pyproject_without_project_table():
    assert parse_pyproject("[tool.ruff]\nline-length = 88\n") == []


# --- requirements.txt --------------------------------------------------------


def test_requirements_skips_comments_options_and_urls():
    text = """
# web stack
Django>=5.0  # pinned below 6
requests[socks]==2.32.3
-r base.txt
--index-url https://example.org/simple
-e .
git+https://github.com/org/repo.git
./local-package
"""

    assert parse_requirements(text) == [Dependency("django"), Dependency("requests")]


@pytest.mark.parametrize(
    ("requirement", "name"),
    [
        ("Flask", "flask"),
        ("Flask_SQLAlchemy>=3", "flask-sqlalchemy"),
        ("zope.interface", "zope-interface"),
        ("pkg @ https://example.org/pkg.whl", "pkg"),
        ("https://example.org/pkg.whl", None),
        ("", None),
    ],
)
def test_python_name(requirement, name):
    assert python_name(requirement) == name


# --- detect_manifests --------------------------------------------------------


def test_finds_manifests_in_subdirectories(tmp_path):
    write(tmp_path, "web/package.json", '{"dependencies": {"vue": "3"}}')
    write(tmp_path, "api/requirements.txt", "flask\n")
    write(tmp_path, "api/requirements-dev.txt", "pytest\n")

    manifests, warnings = detect(
        tmp_path, "api/requirements-dev.txt", "api/requirements.txt", "web/package.json"
    )

    assert manifests == (
        Manifest(
            PurePosixPath("api/requirements-dev.txt"),
            Ecosystem.PYTHON,
            (Dependency("pytest", dev=True),),
        ),
        Manifest(
            PurePosixPath("api/requirements.txt"),
            Ecosystem.PYTHON,
            (Dependency("flask"),),
        ),
        Manifest(
            PurePosixPath("web/package.json"), Ecosystem.NPM, (Dependency("vue"),)
        ),
    )
    assert warnings == ()


def test_other_manifests_are_detected_but_not_parsed(tmp_path):
    write(tmp_path, "go.mod", "module example.com/app\n")

    manifests, _ = detect(tmp_path, "go.mod")

    assert manifests == (Manifest(PurePosixPath("go.mod"), Ecosystem.GO, parsed=False),)


def test_invalid_manifest_becomes_a_warning(tmp_path):
    write(tmp_path, "package.json", '{"dependencies": {"react": "1"')

    manifests, warnings = detect(tmp_path, "package.json")

    assert manifests[0].parsed is False
    assert len(warnings) == 1
    assert warnings[0].startswith("Could not parse package.json:")


def test_parse_warning_never_includes_file_contents(tmp_path):
    write(tmp_path, "package.json", '{"token": "super-secret-value" oops}')

    _, warnings = detect(tmp_path, "package.json")

    assert "super-secret-value" not in warnings[0]


def test_duplicate_dependency_keeps_runtime_entry(tmp_path):
    text = """
[project]
dependencies = ["rich"]
[project.optional-dependencies]
dev = ["rich", "pytest"]
test = ["pytest"]
"""
    write(tmp_path, "pyproject.toml", text)

    manifests, _ = detect(tmp_path, "pyproject.toml")

    assert manifests[0].dependencies == (
        Dependency("rich"),
        Dependency("pytest", dev=True),
    )


def test_ignores_files_that_are_not_manifests(tmp_path):
    write(tmp_path, "notes.txt", "react")

    assert detect(tmp_path, "notes.txt") == ((), ())
