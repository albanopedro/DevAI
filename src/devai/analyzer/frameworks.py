"""Recognize frameworks from the dependencies a project declares."""

from collections.abc import Iterable

from devai.models import Ecosystem, Manifest

# Dependency name (normalized) → framework, per ecosystem.
FRAMEWORKS = {
    Ecosystem.NPM: {
        "react": "React",
        "react-native": "React Native",
        "next": "Next.js",
        "vue": "Vue",
        "nuxt": "Nuxt",
        "svelte": "Svelte",
        "@sveltejs/kit": "SvelteKit",
        "@angular/core": "Angular",
        "solid-js": "Solid",
        "astro": "Astro",
        "express": "Express",
        "fastify": "Fastify",
        "koa": "Koa",
        "hono": "Hono",
        "@nestjs/core": "NestJS",
        "electron": "Electron",
        "vite": "Vite",
        "tailwindcss": "Tailwind CSS",
        "bootstrap": "Bootstrap",
    },
    Ecosystem.PYTHON: {
        "fastapi": "FastAPI",
        "django": "Django",
        "flask": "Flask",
        "streamlit": "Streamlit",
    },
}

TEST_FRAMEWORKS = {
    Ecosystem.NPM: {
        "jest": "Jest",
        "vitest": "Vitest",
        "mocha": "Mocha",
        "cypress": "Cypress",
        "@playwright/test": "Playwright",
    },
    Ecosystem.PYTHON: {
        "pytest": "pytest",
        "nose2": "nose2",
    },
}


def detect_frameworks(manifests: Iterable[Manifest]) -> tuple[str, ...]:
    return match_dependencies(manifests, FRAMEWORKS)


def detect_test_frameworks(manifests: Iterable[Manifest]) -> tuple[str, ...]:
    return match_dependencies(manifests, TEST_FRAMEWORKS)


def match_dependencies(
    manifests: Iterable[Manifest], tables: dict[Ecosystem, dict[str, str]]
) -> tuple[str, ...]:
    """Names from `tables` matching any dependency, unique and sorted."""
    found = set()
    for manifest in manifests:
        known = tables.get(manifest.ecosystem, {})
        found.update(
            known[dependency.name]
            for dependency in manifest.dependencies
            if dependency.name in known
        )
    return tuple(sorted(found, key=str.lower))
