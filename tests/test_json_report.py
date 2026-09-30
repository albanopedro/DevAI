import json

from conftest import FAKE_SECRETS, make_files

from devai import __version__
from devai.analyzer import analyze_project
from devai.checks import run_checks
from devai.json_report import SCHEMA_VERSION, to_json


def render(project):
    info = analyze_project(project)
    return to_json(info, run_checks(info))


def test_json_document_structure(tmp_path):
    make_files(tmp_path, "src/app.py", "README.md")

    document = json.loads(render(tmp_path))

    assert document["schema_version"] == SCHEMA_VERSION == 1
    assert document["devai_version"] == __version__
    assert document["project"]["name"] == tmp_path.name
    assert document["project"]["path"] == str(tmp_path.resolve())
    assert document["project"]["file_source"] == "filesystem"
    assert document["project"]["files"] == ["README.md", "src/app.py"]
    assert document["project"]["languages"] == [{"name": "Python", "files": 1}]


def test_json_findings(tmp_path):
    secret, _ = FAKE_SECRETS["secret/github-token"]
    make_files(tmp_path, "config.js")
    (tmp_path / "config.js").write_text(f"const token = '{secret}';\n")

    output = render(tmp_path)
    findings = json.loads(output)["checks"]["findings"]

    assert findings[0] == {
        "rule_id": "secret/github-token",
        "severity": "high",
        "message": "Possible GitHub token",
        "file": "config.js",
        "line": 1,
        "evidence": "ghp_…",
    }
    assert secret not in output
