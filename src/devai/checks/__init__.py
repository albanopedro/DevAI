"""Checks judge what the analyzer found and report problems as Findings.

Layering: checks depend on the analyzer, never the other way around (D024).
"""

from devai.checks.runner import run_checks

__all__ = ["run_checks"]
