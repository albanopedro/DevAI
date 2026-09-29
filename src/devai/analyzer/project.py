"""Run every analyzer step and assemble a ProjectInfo."""

from pathlib import Path, PurePosixPath

from devai.analyzer.files import list_project_files
from devai.analyzer.languages import detect_languages
from devai.analyzer.structure import summarize_structure
from devai.models import FileSource, ProjectInfo


def analyze_project(path: Path) -> ProjectInfo:
    """Analyze the project at `path`.

    Raises NotADirectoryError if `path` is not an existing directory.
    """
    root = path.resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    listing = list_project_files(root)
    has_git = listing.source is FileSource.GIT
    directories, root_file_count = summarize_structure(listing.files)

    warnings = []
    if (root / ".git").exists() and not has_git:
        warnings.append(
            "A .git directory exists but git could not read it; "
            "files were listed from the filesystem instead."
        )

    return ProjectInfo(
        name=root.name,
        path=root,
        file_count=len(listing.files),
        file_source=listing.source,
        has_git=has_git,
        has_readme=has_readme(listing.files),
        languages=detect_languages(listing.files),
        directories=directories,
        root_file_count=root_file_count,
        warnings=tuple(warnings),
    )


def has_readme(files: list[PurePosixPath]) -> bool:
    """Return True if a README file (any extension or case) is at the root."""
    return any(
        len(path.parts) == 1 and path.name.lower().startswith("readme")
        for path in files
    )
