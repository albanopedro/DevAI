"""Find well-known configuration files by name. Their contents are never read."""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

CONFIG_FILE_NAMES = frozenset(
    {
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        ".nvmrc",
        ".python-version",
        ".pre-commit-config.yaml",
        "Dockerfile",
        ".dockerignore",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "Makefile",
        "tsconfig.json",
        "jsconfig.json",
        "vercel.json",
        "netlify.toml",
        "setup.cfg",
        "tox.ini",
        "pytest.ini",
    }
)

CONFIG_FILE_PATTERN = re.compile(
    r"\.env(\..+)?"  # .env, .env.example, .env.local ...
    r"|(vite|vitest|next|nuxt|svelte|astro|eslint|prettier|tailwind|postcss"
    r"|webpack|rollup|babel|jest|playwright)\.config\.[cm]?[jt]s"
    r"|\.(eslintrc|prettierrc)(\..+)?"
)


def detect_config_files(files: Iterable[PurePosixPath]) -> tuple[PurePosixPath, ...]:
    return tuple(path for path in files if is_config_file(path))


def is_config_file(path: PurePosixPath) -> bool:
    if path.parts[:2] == (".github", "workflows"):
        return path.suffix in {".yml", ".yaml"}
    return (
        path.name in CONFIG_FILE_NAMES
        or CONFIG_FILE_PATTERN.fullmatch(path.name) is not None
    )
