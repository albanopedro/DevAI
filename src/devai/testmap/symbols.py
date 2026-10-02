"""Find public Python functions and classes no test file mentions (D045).

A hint, not a measurement: a symbol tested indirectly, or whose name is a
common word, can look tested or untested by mistake.
"""

import ast
import re


class NotPython(Exception):
    """The file couldn't be parsed as Python."""


def public_symbols(text: str) -> list[str]:
    """Top-level functions and classes whose names don't start with "_"."""
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise NotPython(str(error)) from error
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and not node.name.startswith("_")
    ]


def unmentioned(symbols: list[str], tests_text: str) -> list[str]:
    """Symbols whose name never appears, as a whole word, in the tests."""
    return [
        name for name in symbols if not re.search(rf"\b{re.escape(name)}\b", tests_text)
    ]
