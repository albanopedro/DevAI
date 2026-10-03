"""Place JSDoc above JavaScript/TypeScript exports (D049).

A /** */ block goes right above the export, or above its decorators, with
the export's indentation. The targets are the exports `devai docs` finds
(D048). There is no JavaScript parser here, so the guarantee comes from the
block itself: the text can't contain "*/", so each block is exactly one
comment, opened on its first line and closed on its last, with no code.
"""

from devai.docgen.lines import WIDTH, Target, leading_whitespace, split_lines, wrap_text
from devai.docmap.js_docs import exported_name, has_jsdoc_above


def js_targets(text: str) -> list[Target]:
    """A target for each exported function or class without JSDoc, in file order."""
    lines = [line.rstrip("\r\n") for line in split_lines(text)]
    first: dict[str, int] = {}
    documented: dict[str, bool] = {}
    for number, line in enumerate(lines):
        name = exported_name(line)
        if name is None:
            continue
        # TypeScript overloads repeat a name: docs go above the first one.
        first.setdefault(name, number)
        documented[name] = documented.get(name, False) or has_jsdoc_above(lines, number)

    targets = []
    for name, number in first.items():
        if documented[name]:
            continue
        while number > 0 and lines[number - 1].lstrip().startswith("@"):
            number -= 1  # above the decorators
        targets.append(Target(name, number, leading_whitespace(lines[number])))
    return targets


def format_jsdoc(text: str, indent: str) -> list[str]:
    """The comment's lines (no line endings) for clean `text` without "*/"."""
    width = max(40, WIDTH - len(indent) - len(" * "))
    content = wrap_text(text, width)
    one_line = f"{indent}/** {content[0]} */"
    if len(content) == 1 and len(one_line) <= WIDTH:
        return [one_line]
    return [
        f"{indent}/**",
        *(f"{indent} * {line}" if line else f"{indent} *" for line in content),
        f"{indent} */",
    ]


def is_one_comment(block: list[str]) -> bool:
    """True if the lines are exactly one /** */ comment and nothing else."""
    joined = "\n".join(block)
    return (
        joined.lstrip().startswith("/**")
        and joined.rstrip().endswith("*/")
        and joined.count("*/") == 1
    )
