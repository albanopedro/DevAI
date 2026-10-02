from pathlib import Path, PurePosixPath

import pytest
from conftest import write

from devai.chat.retrieval import ChatError, question_terms, select_files


@pytest.fixture
def project(tmp_path):
    write(tmp_path, "api/users.py", "def get_user(user_id):\n    raise Error(500)\n")
    write(tmp_path, "api/orders.py", "def list_orders():\n    return []\n")
    write(tmp_path, "README.md", "This API serves users and orders.\n")
    write(tmp_path, "docs/notes.md", "nothing relevant here\n")
    return tmp_path


def paths(selection):
    return [str(file.path) for file in selection.files]


# --- terms ------------------------------------------------------------------------


def test_terms_drop_stopwords_short_words_and_duplicates():
    question = "Por que a API /users retorna 500 quando o getUser falha? Users!"

    assert question_terms(question) == ("api", "users", "500", "getuser", "falha")


def test_english_stopwords_too():
    assert question_terms("Why does the login fail with this token?") == (
        "login",
        "fail",
        "token",
    )


# --- ranking --------------------------------------------------------------------


def test_path_matches_rank_above_content_matches(project):
    selection = select_files(project, "why do users get 500?")

    assert paths(selection)[0] == "api/users.py"
    assert "README.md" in paths(selection)
    assert "docs/notes.md" not in paths(selection)


def test_reasons_name_the_matched_terms(project):
    [first, *_] = select_files(project, "users 500").files

    assert first.reason == "matches: users, 500"


def test_no_terms_means_no_files(project):
    assert select_files(project, "why is it so?").files == ()


def test_limit(project):
    assert len(select_files(project, "api users orders", limit=2).files) == 2


# --- privacy -------------------------------------------------------------------------


def test_sensitive_and_unreadable_files_are_never_picked(project):
    write(project, ".env", "users=500\n")
    write(project, "package-lock.json", '{"users": 500}\n')
    write(project, "big.txt", "users " * 300_000)
    (project / "logo.png").write_bytes(b"\x89PNG\0users")
    (project / "link.py").symlink_to(project / "api" / "users.py")

    picked = paths(select_files(project, "users", limit=10))

    for name in [".env", "package-lock.json", "big.txt", "logo.png", "link.py"]:
        assert name not in picked


def test_gitignored_files_are_never_picked(project):
    write(project, ".gitignore", "secrets/\n")
    write(project, "secrets/users.txt", "users users users\n")

    assert "secrets/users.txt" not in paths(select_files(project, "users", limit=10))


# --- files named with --file -------------------------------------------------------


def test_named_files_come_first(project):
    selection = select_files(project, "users", extra_files=("docs/notes.md",))

    assert paths(selection)[0] == "docs/notes.md"
    assert selection.files[0].reason == "added with --file"
    assert paths(selection).count("docs/notes.md") == 1


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("../outside.py", "outside the project"),
        ("missing.py", "no such file"),
        (".env", "never sent"),
        ("package-lock.json", "never sent"),
        ("secrets/key.txt", "ignored by the project's .gitignore"),
        ("logo.png", "binary or larger than 1 MB"),
        ("link.py", "symbolic links are not sent"),
    ],
)
def test_named_files_get_the_same_checks(project, name, message):
    write(project.parent, "outside.py", "x = 1\n")
    write(project, ".env", "X=1\n")
    write(project, "package-lock.json", "{}\n")
    write(project, ".gitignore", "secrets/\n")
    write(project, "secrets/key.txt", "k\n")
    (project / "logo.png").write_bytes(b"\x89PNG\0")
    (project / "link.py").symlink_to(project / "api" / "users.py")

    with pytest.raises(ChatError, match=message):
        select_files(project, "q", extra_files=(name,))


def test_absolute_path_inside_the_project_is_accepted(project):
    absolute = str(project / "api" / "orders.py")

    selection = select_files(project, "q", extra_files=(absolute,))

    assert selection.files[0].path == PurePosixPath("api/orders.py")


def test_selected_text_is_kept_for_the_context(project):
    [first, *_] = select_files(project, "users").files

    assert first.text == (Path(project) / "api/users.py").read_text()
