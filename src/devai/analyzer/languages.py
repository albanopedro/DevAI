"""Detect programming languages from file extensions."""

from collections import Counter
from collections.abc import Iterable
from pathlib import PurePosixPath

from devai.models import LanguageStat

# Data and docs formats (JSON, YAML, Markdown...) are deliberately left out.
# JSX/TSX count as JavaScript/TypeScript, as GitHub does.
EXTENSION_LANGUAGES = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SCSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".swift": "Swift",
    ".dart": "Dart",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".sql": "SQL",
}


def language_for(path: PurePosixPath) -> str | None:
    return EXTENSION_LANGUAGES.get(path.suffix.lower())


def detect_languages(files: Iterable[PurePosixPath]) -> tuple[LanguageStat, ...]:
    """Count files per language, most common first (ties sorted by name)."""
    counts = Counter(
        language for path in files if (language := language_for(path)) is not None
    )
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(LanguageStat(name, total) for name, total in ranked)
