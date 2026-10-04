"""AI tasks for the web: prepare, send, apply (D051). No FastAPI here.

Each task is built from the same pieces as its CLI command, so a page and the
terminal send the same context and get the same checks:

- prepare: everything `--dry-run` shows (the exact context, where it goes),
  and nothing is sent;
- send: only after the user's click on that preview; the answer is checked
  like in the CLI and becomes the same JSON as `--format json`;
- apply: only after a second click on the diff. The content written is the
  one kept here on the server; a page only names it by its id. The checks of
  D044 (writes) and D047 (new files) run again right before writing.

The chat stays in the terminal: it asks for file approval at every question.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Any

from devai.ai import build_context, estimate_tokens, serialize_context
from devai.ai.result import AIRequest, AIResult, LLMClient
from devai.ai.settings import AISettings
from devai.analyzer import analyze_project
from devai.analyzer.files import list_project_files
from devai.chat.retrieval import ChatError, SelectedFile, extra_file
from devai.checks import run_checks
from devai.checks.secrets import read_scannable_text
from devai.docgen.context import build_docs_context
from devai.docgen.plan import DocsError, find_targets, plan_docs
from devai.docmap import doc_sources
from devai.docmap.python_docs import NotPython
from devai.docmap.readme import MARKDOWN_SUFFIXES, find_readme, readme_map
from devai.fix.context import MAX_FIX_FILES, build_fix_context
from devai.fix.edits import FileChange
from devai.json_report import (
    doc_proposal_to_json,
    fix_to_json,
    generated_tests_to_json,
    readme_proposal_to_json,
    review_to_json,
    to_json,
)
from devai.readmegen.context import build_readme_context, project_facts, readme_topics
from devai.readmegen.plan import ReadmeError, plan_readme
from devai.review import ReviewError, collect_changes, review_report, run_review_checks
from devai.review.context import build_review_context
from devai.testgen.context import build_testgen_context
from devai.testgen.create import run_command
from devai.testmap import build_coverage_map
from devai.testmap.pairing import covers, source_files, test_files

TASKS = ("analysis", "review", "docs", "readme", "fix", "tests")
MAX_REQUEST_CHARACTERS = 2_000  # what a fix request may say


class TaskError(Exception):
    """The task can't go on. The message is safe to show."""


@dataclass(frozen=True)
class Action:
    """What applying an outcome would do."""

    kind: str  # "write" (existing files, D044) or "create" (a new file, D047)
    changes: tuple[FileChange, ...] = ()  # write
    sources: tuple[SelectedFile, ...] = ()  # write: the files as they were read
    path: PurePosixPath | None = None  # create
    content: str = ""  # create

    @property
    def files(self) -> list[str]:
        if self.kind == "create":
            return [str(self.path)]
        return [str(change.path) for change in self.changes]


@dataclass
class Prepared:
    task: str
    root: Path
    settings: AISettings
    context: dict[str, Any]
    question: str
    request: Callable[[dict[str, Any]], AIRequest]
    finish: Callable[["Prepared", AIResult], "Outcome"]
    state: dict[str, Any] = field(default_factory=dict)

    def preview(self) -> dict[str, Any]:
        """What the page shows before anything is sent."""
        compact = serialize_context(self.context)
        return {
            "task": self.task,
            "question": self.question,
            "destination": self.settings.destination,
            "leaves_machine": self.settings.leaves_machine,
            "data_note": self.settings.data_note,
            "context": self.context,
            "characters": len(compact),
            "tokens": estimate_tokens(compact),
            "redacted_lines": self.context.get("redacted_lines", 0),
        }


@dataclass
class Outcome:
    task: str
    root: Path
    document: dict[str, Any]  # the same JSON as the CLI's --format json
    action: Action | None = None


def prepare(task: str, root: Path, settings: AISettings, params: dict) -> Prepared:
    """Build what would be sent for `task`. Nothing leaves the machine here."""
    builders = {
        "analysis": prepare_analysis,
        "review": prepare_review,
        "docs": prepare_docs,
        "readme": prepare_readme,
        "fix": prepare_fix,
        "tests": prepare_tests,
    }
    if task not in builders:
        raise TaskError(f"unknown task {task!r}; one of: {', '.join(TASKS)}")
    try:
        return builders[task](root, settings, params)
    except ChatError as problem:  # a file that can't be sent (D039 rules)
        raise TaskError(str(problem)) from None
    except NotADirectoryError:
        raise TaskError(f"not a directory: {root}") from None


def send(prepared: Prepared, client: LLMClient) -> Outcome:
    """Send the prepared context and check the answer like the CLI does.

    Raises AIError if the model call fails.
    """
    result = client.complete(prepared.request(prepared.context))
    return prepared.finish(prepared, result)


def apply(outcome: Outcome) -> dict[str, Any]:
    """Write the outcome's change after the checks of D044 or D047, run again now."""
    from devai.fix.apply import ApplyError, WriteError, apply_changes, check_can_apply
    from devai.testgen.create import CreateError, create_test_file, undo_command

    action = outcome.action
    if action is None:
        raise TaskError("there is nothing to apply")
    if action.kind == "create":
        try:
            created = create_test_file(outcome.root, action.path, action.content)
        except CreateError as problem:
            raise TaskError(str(problem)) from None
        return {"files": action.files, "undo": undo_command(action.path, created)}

    try:
        check_can_apply(outcome.root, list(action.sources))
        apply_changes(outcome.root, list(action.changes))
    except (ApplyError, WriteError) as problem:
        raise TaskError(str(problem)) from None
    return {"files": action.files, "undo": "git restore " + " ".join(action.files)}


def blocked(outcome: Outcome) -> str | None:
    """Why applying would be refused right now, or None (the page disables it)."""
    from devai.fix.apply import ApplyError, check_can_apply

    action = outcome.action
    if action is None:
        return None
    if action.kind == "create":
        if (outcome.root / action.path).exists():
            return f"{action.path} already exists"
        return None
    try:
        check_can_apply(outcome.root, list(action.sources))
    except ApplyError as problem:
        return str(problem)
    return None


# --- analysis and review (nothing to apply) -------------------------------------------


def prepare_analysis(root: Path, settings: AISettings, params: dict) -> Prepared:
    from devai.ai.analysis import analysis_request

    info = analyze_project(root)
    checks = run_checks(info)
    context = build_context(info, checks)
    tokens = estimate_tokens(serialize_context(context))
    question = (
        f"Send a project summary (~{tokens:,} tokens, no source code) to "
        f"{settings.destination}?"
    )

    def finish(prepared: Prepared, result: AIResult) -> Outcome:
        return Outcome("analysis", root, json.loads(to_json(info, checks, result)))

    return Prepared(
        "analysis", root, settings, context, question, analysis_request, finish
    )


def prepare_review(root: Path, settings: AISettings, params: dict) -> Prepared:
    from devai.review.ai import ground_issues, review_question, review_request

    try:
        changes = collect_changes(root)
    except ReviewError as problem:
        raise TaskError(str(problem)) from None
    checks = run_review_checks(changes)
    context = build_review_context(changes, checks)
    if not context["diffs"]:
        raise TaskError("there are no code changes that can be sent for review")

    def finish(prepared: Prepared, result: AIResult) -> Outcome:
        report, discarded = ground_issues(result.report, context)
        grounded = replace(result, report=report)
        document = review_to_json(review_report(changes, checks), grounded, discarded)
        return Outcome("review", root, json.loads(document))

    question = review_question(context, settings)
    return Prepared("review", root, settings, context, question, review_request, finish)


# --- docstrings and README ------------------------------------------------------------


def prepare_docs(root: Path, settings: AISettings, params: dict) -> Prepared:
    from devai.docgen.ai import docs_question, docs_request

    info = analyze_project(root)
    source = extra_file(info.path, required(params, "file"), info.files, "named file")
    if not doc_sources((source.path,)):
        raise TaskError(
            f"{source.path}: docs can be written for Python, JavaScript or "
            "TypeScript source files (not tests or config files)"
        )
    try:
        targets = find_targets(source.path, source.text)
    except NotPython:
        raise TaskError(f"{source.path} isn't valid Python") from None
    context = build_docs_context(source, targets, info, run_checks(info))
    if not context["names"]:
        raise TaskError(f"{source.path} has nothing DevAI can document")

    def finish(prepared: Prepared, result: AIResult) -> Outcome:
        texts = [(doc.name, doc.text) for doc in result.report.docs]
        try:
            plan = plan_docs(source.path, source.text, texts, context["names"])
        except DocsError as problem:
            document = doc_proposal_to_json(
                info.name, context, result, None, str(problem)
            )
            return Outcome("docs", root, json.loads(document))
        document = doc_proposal_to_json(info.name, context, result, plan, None)
        action = None
        if plan.change is not None:
            action = Action("write", changes=(plan.change,), sources=(source,))
        return Outcome("docs", root, json.loads(document), action)

    question = docs_question(context, settings)
    return Prepared("docs", root, settings, context, question, docs_request, finish)


def prepare_readme(root: Path, settings: AISettings, params: dict) -> Prepared:
    from devai.readmegen.ai import readme_question, readme_request

    info = analyze_project(root)
    readme_path = find_readme(info.files)
    source, text, readme = None, None, None
    if readme_path is not None:
        if readme_path.suffix.lower() not in MARKDOWN_SUFFIXES:
            raise TaskError(f"{readme_path}: only Markdown READMEs can be extended")
        source = extra_file(info.path, str(readme_path), info.files, "the README")
        text = source.text
        readme = readme_map(readme_path, text, info.path, info.files)
    topics, left_out = readme_topics(info, readme)
    if not topics:
        reasons = "; ".join(f"{topic}: {why}" for topic, why in left_out)
        detail = f" ({reasons})" if reasons else ""
        raise TaskError(f"the README needs no section DevAI can ask for{detail}")
    context = build_readme_context(info, run_checks(info), readme_path, text, topics)

    def finish(prepared: Prepared, result: AIResult) -> Outcome:
        proposal = result.report
        try:
            plan = plan_readme(
                readme_path or PurePosixPath("README.md"),
                text,
                [(s.topic, s.heading, s.body) for s in proposal.sections],
                proposal.description,
                topics,
                info.name,
                project_facts(info),
                info.path,
                info.files,
            )
        except ReadmeError as problem:
            document = readme_proposal_to_json(
                info.name, context, result, None, str(problem)
            )
            return Outcome("readme", root, json.loads(document))
        document = json.loads(
            readme_proposal_to_json(info.name, context, result, plan, None)
        )
        document["left_out"] = [{"topic": t, "reason": why} for t, why in left_out]
        action = None
        if plan.change is not None and plan.creates:
            action = Action("create", path=plan.change.path, content=plan.change.after)
        elif plan.change is not None:
            action = Action("write", changes=(plan.change,), sources=(source,))
        return Outcome("readme", root, document, action)

    question = readme_question(context, settings)
    return Prepared("readme", root, settings, context, question, readme_request, finish)


# --- fixes and tests ------------------------------------------------------------------


def prepare_fix(root: Path, settings: AISettings, params: dict) -> Prepared:
    from devai.fix.ai import fix_question, fix_request
    from devai.fix.edits import FixError, apply_edits

    ask = required(params, "ask")
    names = params.get("files") or []
    if not 1 <= len(names) <= MAX_FIX_FILES:
        raise TaskError(f"name 1 to {MAX_FIX_FILES} files to change")
    info = analyze_project(root)
    allowed = list_project_files(info.path).files
    files = [extra_file(info.path, name, allowed, "named file") for name in names]
    context = build_fix_context(ask, info, run_checks(info), files)

    def finish(prepared: Prepared, result: AIResult) -> Outcome:
        try:
            changes = apply_edits(result.report, {f.path: f.text for f in files})
        except FixError as problem:
            document = fix_to_json(info.name, context, result, [], str(problem))
            return Outcome("fix", root, json.loads(document))
        document = fix_to_json(info.name, context, result, changes, None)
        action = None
        if changes:
            action = Action("write", changes=tuple(changes), sources=tuple(files))
        return Outcome("fix", root, json.loads(document), action)

    question = fix_question(context, settings)
    return Prepared("fix", root, settings, context, question, fix_request, finish)


def prepare_tests(root: Path, settings: AISettings, params: dict) -> Prepared:
    from devai.testgen.ai import generation_question, generation_request
    from devai.testgen.validate import TestGenError, validate_generated

    info = analyze_project(root)
    source = extra_file(info.path, required(params, "file"), info.files, "named file")
    if source.path not in source_files([source.path]):
        raise TaskError(
            f"{source.path}: tests can be written for Python, JavaScript or "
            "TypeScript source files"
        )
    existing = []
    for test_path in test_files(info.files):
        if covers(test_path, source.path):
            text = read_scannable_text(info.path / test_path, test_path)
            if text is not None:
                existing.append(SelectedFile(test_path, "existing test", text))
    untested = dict(build_coverage_map(info).untested_symbols).get(source.path, ())
    context = build_testgen_context(
        source, existing, list(untested), info, run_checks(info)
    )

    def finish(prepared: Prepared, result: AIResult) -> Outcome:
        try:
            path = validate_generated(result.report, info.path, source.path)
        except TestGenError as problem:
            document = generated_tests_to_json(
                info.name, context, result, None, str(problem)
            )
            return Outcome("tests", root, json.loads(document))
        document = json.loads(
            generated_tests_to_json(info.name, context, result, path, None)
        )
        document["run_command"] = run_command(info.tests.frameworks, path)
        action = Action("create", path=path, content=result.report.content)
        return Outcome("tests", root, document, action)

    question = generation_question(context, settings)
    return Prepared(
        "tests", root, settings, context, question, generation_request, finish
    )


def required(params: dict, name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value.strip():
        raise TaskError(f"{name!r} is required for this task")
    if len(value) > MAX_REQUEST_CHARACTERS:
        raise TaskError(f"{name!r} is too long")
    return value.strip()
