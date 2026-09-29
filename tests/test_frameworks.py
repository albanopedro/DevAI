from pathlib import PurePosixPath

from devai.analyzer.frameworks import detect_frameworks, detect_test_frameworks
from devai.models import Dependency, Ecosystem, Manifest


def manifest(ecosystem, *names, dev=False):
    dependencies = tuple(Dependency(name, dev) for name in names)
    return Manifest(PurePosixPath("m"), ecosystem, dependencies)


def test_detects_frameworks_across_manifests_sorted_by_name():
    manifests = [
        manifest(Ecosystem.NPM, "react", "react-dom", "express"),
        manifest(Ecosystem.NPM, "vite", dev=True),
        manifest(Ecosystem.PYTHON, "django", "requests"),
    ]

    assert detect_frameworks(manifests) == ("Django", "Express", "React", "Vite")


def test_matching_is_per_ecosystem():
    # A Python package called "react" is not the React framework.
    assert detect_frameworks([manifest(Ecosystem.PYTHON, "react")]) == ()


def test_each_framework_listed_once():
    manifests = [manifest(Ecosystem.NPM, "react"), manifest(Ecosystem.NPM, "react")]

    assert detect_frameworks(manifests) == ("React",)


def test_detects_test_frameworks():
    manifests = [
        manifest(Ecosystem.PYTHON, "pytest", dev=True),
        manifest(Ecosystem.NPM, "vitest", "@playwright/test", dev=True),
    ]

    assert detect_test_frameworks(manifests) == ("Playwright", "pytest", "Vitest")


def test_no_frameworks():
    assert detect_frameworks([]) == ()
