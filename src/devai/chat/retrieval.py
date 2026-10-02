"""Pick the project files most relevant to a question, locally and without AI.

Deterministic keyword matching (D039): the question's terms are looked up in
each file's path (worth more) and content (capped, so a huge file can't
dominate). Only files the privacy rules allow are read (D021), and only
files the project's ignore rules keep: what git would ignore stays out.
Every pick comes with its reason, so the user can judge it.
"""

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from devai.analyzer.files import list_project_files
from devai.checks.secrets import is_skipped_by_name, read_scannable_text

MAX_SELECTED_FILES = 5
PATH_MATCH_POINTS = 5
MAX_CONTENT_POINTS_PER_TERM = 5

# Identifiers and words of 3+ characters, and numbers of 3+ digits ("500").
TERM = re.compile(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]{2,}|\d{3,}")

# Words that say nothing about where the answer is (Portuguese and English).
STOPWORDS = frozenset(
    """
    por que porque para com uma umas uns como onde quando qual quais quem isso
    essa esse esta este isto aqui ali está estão são ser foi tem têm não sim
    mais menos dos das nos nas num numa pelo pela pelos pelas sobre entre
    depois antes ainda também muito muita fazer faz feito pode posso deve meu
    minha seu sua fica ficam funciona funcionam retorna retornam acontece
    existe usa usar the and for why what how does did this that these those
    with from when where which there here into are was were can could should
    would will not but its our your you have has had work works happen
    happens used
    """.split()
)


class ChatError(Exception):
    """A requested file can't be used; the message is safe to show."""


@dataclass(frozen=True)
class SelectedFile:
    path: PurePosixPath
    reason: str  # why it was picked: matched terms, or "added with --file"
    text: str  # kept in memory to build the context; never printed


@dataclass(frozen=True)
class Selection:
    terms: tuple[str, ...]
    files: tuple[SelectedFile, ...]


def select_files(
    root: Path,
    question: str,
    extra_files: tuple[str, ...] = (),
    limit: int = MAX_SELECTED_FILES,
) -> Selection:
    """The files to send with `question`: those the user named, then the best matches.

    Raises ChatError if a file named in `extra_files` can't be used.
    """
    allowed = list_project_files(root).files
    chosen = [extra_file(root, name, allowed) for name in extra_files]

    terms = question_terms(question)
    taken = {file.path for file in chosen}
    for path, _score, matched in rank(root, allowed, terms):
        if len(chosen) >= limit:
            break
        if path in taken:
            continue
        text = read_scannable_text(root / path, path)
        if text is not None:
            chosen.append(SelectedFile(path, f"matches: {', '.join(matched)}", text))
    return Selection(terms=terms, files=tuple(chosen))


def question_terms(question: str) -> tuple[str, ...]:
    """Distinct lowercase search terms, in order, without stopwords."""
    terms = []
    for match in TERM.finditer(question):
        term = match.group().lower()
        if term not in STOPWORDS and term not in terms:
            terms.append(term)
    return tuple(terms)


def rank(
    root: Path, files: list[PurePosixPath], terms: tuple[str, ...]
) -> list[tuple[PurePosixPath, int, list[str]]]:
    """Files with a positive score, best first: (path, score, matched terms)."""
    if not terms:
        return []
    scored = []
    for path in files:
        if is_skipped_by_name(path):
            continue
        text = read_scannable_text(root / path, path)
        if text is None:
            continue  # binary, large, symlink: never read
        name = str(path).lower()
        content = text.lower()
        score = 0
        matched = []
        for term in terms:
            points = PATH_MATCH_POINTS if term in name else 0
            points += min(content.count(term), MAX_CONTENT_POINTS_PER_TERM)
            if points:
                score += points
                matched.append(term)
        if score:
            scored.append((path, score, matched))
    return sorted(scored, key=lambda item: (-item[1], str(item[0])))


def extra_file(root: Path, name: str, allowed: list[PurePosixPath]) -> SelectedFile:
    """A file the user named with --file, after the same checks as any other."""
    given = Path(name)
    candidate = given if given.is_absolute() else root / given
    if candidate.is_symlink():
        raise ChatError(f"{name}: symbolic links are not sent")
    try:
        relative = PurePosixPath(candidate.resolve().relative_to(root).as_posix())
    except ValueError:
        raise ChatError(f"{name}: outside the project") from None
    if not candidate.is_file():
        raise ChatError(f"{name}: no such file in the project")
    if is_skipped_by_name(relative):
        raise ChatError(f"{name}: never sent (environment, lock or minified file)")
    if relative not in allowed:
        raise ChatError(f"{name}: ignored by the project's .gitignore")
    text = read_scannable_text(root / relative, relative)
    if text is None:
        raise ChatError(f"{name}: binary or larger than 1 MB")
    return SelectedFile(relative, "added with --file", text)
