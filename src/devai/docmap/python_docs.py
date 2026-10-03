"""Find public Python names without a docstring, with `ast` (D048).

Checked: the module itself, public top-level functions and classes, and the
public methods of public classes. A name is public when it doesn't start
with "_", so __init__ and other special methods are skipped.
"""

import ast

MODULE = "(module)"  # stands for the module docstring in the lists


class NotPython(Exception):
    """The file couldn't be parsed as Python."""


def python_names(text: str) -> list[tuple[str, bool]]:
    """(name, has a docstring) for each public name, in file order.

    An empty module (no statements) has nothing to document: [].
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise NotPython(str(error)) from error
    if not tree.body:
        return []

    names = [(MODULE, ast.get_docstring(tree) is not None)]
    for node in tree.body:
        if not is_public_definition(node):
            continue
        names.append((node.name, ast.get_docstring(node) is not None))
        if isinstance(node, ast.ClassDef):
            names += [
                (f"{node.name}.{method.name}", ast.get_docstring(method) is not None)
                for method in node.body
                if is_public_definition(method) and not isinstance(method, ast.ClassDef)
            ]
    return merge_repeated(names)


def is_public_definition(node: ast.stmt) -> bool:
    return isinstance(
        node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) and not node.name.startswith("_")


def merge_repeated(names: list[tuple[str, bool]]) -> list[tuple[str, bool]]:
    """One entry per name, documented if any definition is (overloads, setters)."""
    merged: dict[str, bool] = {}
    for name, documented in names:
        merged[name] = merged.get(name, False) or documented
    return list(merged.items())
