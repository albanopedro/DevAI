from pathlib import PurePosixPath

import pytest

from devai.analyzer.config_files import detect_config_files, is_config_file


@pytest.mark.parametrize(
    "path",
    [
        ".gitignore",
        ".env",
        ".env.example",
        ".env.production",
        "Dockerfile",
        "docker-compose.yml",
        "tsconfig.json",
        "vite.config.js",
        "next.config.mjs",
        "eslint.config.js",
        ".eslintrc.json",
        ".prettierrc",
        "vercel.json",
        "backend/Dockerfile",
        ".github/workflows/ci.yml",
    ],
)
def test_recognizes_config_files(path):
    assert is_config_file(PurePosixPath(path)) is True


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",
        "package.json",  # a manifest, reported under Dependencies
        "src/config.ts",
        ".environment",
        ".github/workflows/README.md",
        "docs/.github/workflows/ci.yml",
    ],
)
def test_ignores_other_files(path):
    assert is_config_file(PurePosixPath(path)) is False


def test_detect_keeps_listing_order():
    files = [PurePosixPath(p) for p in [".gitignore", "src/main.js", "vite.config.js"]]

    assert detect_config_files(files) == (
        PurePosixPath(".gitignore"),
        PurePosixPath("vite.config.js"),
    )
