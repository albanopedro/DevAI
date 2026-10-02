"""Check an AI test proposal before showing it (D046).

The whole proposal is rejected, with the reason, if the new file's path
leaves the project, already exists, is ignored, doesn't look like a test
file covering the source (so `devai test` would recognize it), or uses
another language; or if its content is empty, too long, holds a secret or
the redaction marker, or isn't valid Python.
"""

import ast
from pathlib import Path, PurePosixPath

from devai import git
from devai.analyzer.files import is_ignored, load_gitignore
from devai.analyzer.languages import language_for
from devai.analyzer.testing import TEST_FILE_NAME
from devai.checks.secrets import match_line
from devai.testgen.schema import GeneratedTests
from devai.testmap.pairing import covers

MAX_TEST_LINES = 300
REDACTION_MARKER = "[redacted"
JS_FAMILY = frozenset({"JavaScript", "TypeScript"})


class TestGenError(Exception):
    """The proposal was rejected; the message is safe to show."""

    __test__ = False  # not a pytest test class, despite the name


def validate_generated(
    proposal: GeneratedTests, root: Path, source: PurePosixPath
) -> PurePosixPath:
    """The checked project-relative path of the new test file."""
    path = checked_path(proposal.path, root)

    if not has_test_name(path):
        raise TestGenError(
            f"{path} doesn't follow test file naming conventions, so test runners "
            "wouldn't find it"
        )
    if not covers(path, source):
        raise TestGenError(f"{path}'s name doesn't contain {source.name}'s name")
    if not same_language(path, source):
        raise TestGenError(f"{path} isn't in the same language as {source}")

    content = proposal.content
    lines = content.split("\n")
    if not content.strip():
        raise TestGenError("the proposed test file is empty")
    if len(lines) > MAX_TEST_LINES:
        raise TestGenError(
            f"the proposed file is too long ({len(lines)} lines; at most "
            f"{MAX_TEST_LINES})"
        )
    if REDACTION_MARKER in content:
        raise TestGenError("the proposed tests copy a line hidden as a possible secret")
    for number, line in enumerate(lines, start=1):
        finding = match_line(line, include_generic=False)  # tests hold fake passwords
        if finding is not None:
            raise TestGenError(
                f"line {number} of the proposed tests holds a possible secret "
                f"({finding.message})"
            )
    if path.suffix == ".py":
        try:
            ast.parse(content)
        except SyntaxError as error:
            raise TestGenError(
                f"the proposed tests aren't valid Python (line {error.lineno}: "
                f"{error.msg})"
            ) from error
    return path


def checked_path(name: str, root: Path) -> PurePosixPath:
    name = name.strip()
    if not name or Path(name).is_absolute():
        raise TestGenError(f"{name!r} isn't a project-relative path")
    target = root / name
    try:
        relative = PurePosixPath(target.resolve().relative_to(root).as_posix())
    except ValueError:
        raise TestGenError(f"{name} is outside the project") from None
    if target.exists() or target.is_symlink():
        raise TestGenError(f"{relative} already exists; DevAI never overwrites a file")
    if ignored(root, relative):
        raise TestGenError(f"{relative} would be ignored by the project's .gitignore")
    return relative


def ignored(root: Path, path: PurePosixPath) -> bool:
    if git.is_inside_work_tree(root):
        try:
            return git.is_ignored(root, str(path))
        except git.GitError as error:
            # Fail closed: an unanswered question is not a "no".
            raise TestGenError(
                f"couldn't check .gitignore for {path} ({error})"
            ) from error
    spec = load_gitignore(root)
    return is_ignored(spec, path)


def has_test_name(path: PurePosixPath) -> bool:
    """The file NAME must look like a test (test_x.py, x.test.js...), or sit in a
    __tests__ directory: being inside tests/ isn't enough for pytest to find it."""
    return TEST_FILE_NAME.fullmatch(path.name) is not None or "__tests__" in path.parts


def same_language(test: PurePosixPath, source: PurePosixPath) -> bool:
    test_language, source_language = language_for(test), language_for(source)
    if source_language in JS_FAMILY:
        return test_language in JS_FAMILY
    return test_language == source_language
