"""Place docstrings in Python code, and prove the code itself is unchanged (D049).

A docstring goes on the line after the definition's header (after the
`):` of a long signature, before any comment that opens the body), with the
body's indentation. The module's goes before the first statement of the
file, after any leading comments. The same public names as `devai docs`
(D048) are targets. A body written on the definition's line (`def f():
pass`) has no room for a docstring and is skipped.

The proof: parse both versions, drop every docstring, and compare the trees.
Any other difference, even one character of code, fails it.
"""

import ast
import bisect
import io
import tokenize

from devai.docgen.lines import WIDTH, Target, leading_whitespace, split_lines, wrap_text
from devai.docmap.python_docs import MODULE, NotPython, is_public_definition

DOCUMENTED_NODES = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
NOT_CODE = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
    }
)


def python_targets(text: str) -> list[Target]:
    """A target for each public name without a docstring, in file order."""
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise NotPython(str(error)) from error
    if not tree.body:
        return []  # an empty module has nothing to document

    candidates: list[tuple[str, ast.Module | ast.stmt]] = [(MODULE, tree)]
    for node in tree.body:
        if not is_public_definition(node):
            continue
        candidates.append((node.name, node))
        if isinstance(node, ast.ClassDef):
            candidates += [
                (f"{node.name}.{method.name}", method)
                for method in node.body
                if is_public_definition(method) and not isinstance(method, ast.ClassDef)
            ]

    # A name defined twice (a property and its setter) gets docs on the first
    # definition, and only if no definition has them, as in D048.
    first: dict[str, ast.Module | ast.stmt] = {}
    documented: dict[str, bool] = {}
    for name, node in candidates:
        first.setdefault(name, node)
        documented[name] = documented.get(name, False) or has_docstring(node)

    lines = [line.rstrip("\r\n") for line in split_lines(text)]
    code_ends = code_line_ends(text)
    return [
        target_for(name, node, lines, code_ends)
        for name, node in first.items()
        if not documented[name]
    ]


def target_for(
    name: str, node: ast.Module | ast.stmt, lines: list[str], code_ends: list[int]
) -> Target:
    body = node.body[0]
    line = first_line(body)
    if name == MODULE:
        return Target(name, line, "", blank_after=True)
    # Without decorators, code before the body's column means `def f(): pass`.
    inline = not getattr(body, "decorator_list", None) and bool(
        lines[line][: body.col_offset].strip()
    )
    # The header ends on the last line with code before the body: insert after it.
    before_body = bisect.bisect_left(code_ends, line + 1)
    if before_body and not inline:
        line = code_ends[before_body - 1]
    indent = leading_whitespace(lines[first_line(body)])
    return Target(name, line, indent, inline, isinstance(node, ast.ClassDef))


def code_line_ends(text: str) -> list[int]:
    """The last line (1-based) of each code token, in order: comments don't count."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        return [token.end[0] for token in tokens if token.type not in NOT_CODE]
    except (tokenize.TokenError, SyntaxError):
        return []  # then the docs go right before the body; the proof still runs


def first_line(node: ast.stmt) -> int:
    """The statement's first line, 0-based, counting its decorators."""
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *(decorator.lineno for decorator in decorators)]) - 1


def has_docstring(node: ast.AST) -> bool:
    return ast.get_docstring(node, clean=False) is not None


def format_docstring(text: str, indent: str) -> list[str]:
    """The docstring's lines (no line endings) for clean `text`.

    One line if it fits; otherwise the summary on the opening line and the
    closing quotes on their own. Text with a backslash gets r\"\"\", as PEP 257
    advises, so "\\n" stays two characters.
    """
    prefix = 'r"""' if "\\" in text else '"""'
    width = max(40, WIDTH - len(indent) - len(prefix))
    content = wrap_text(text, width)
    one_line = f'{indent}{prefix}{content[0]}"""'
    if (
        len(content) == 1
        and len(one_line) <= WIDTH
        and not content[0].endswith(('"', "\\"))  # would merge with the quotes
    ):
        return [one_line]
    return [
        f"{indent}{prefix}{content[0]}",
        *(f"{indent}{line}" if line else "" for line in content[1:]),
        f'{indent}"""',
    ]


def python_code_unchanged(before: str, after: str) -> bool:
    """True if the two versions differ only in docstrings.

    Raises SyntaxError if `after` isn't valid Python.
    """
    return code_without_docstrings(before) == code_without_docstrings(after)


def code_without_docstrings(text: str) -> str:
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if not isinstance(node, DOCUMENTED_NODES):
            continue
        if node.body and is_docstring(node.body[0]):
            node.body = node.body[1:]
    return ast.dump(tree)  # no line numbers: moved code compares equal, changed doesn't


def is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )
