"""Find exported JavaScript/TypeScript functions and classes without JSDoc (D048).

Python's standard library has no JavaScript parser, so exports are found by
pattern, line by line. An estimate. Found:

- `export [default] [async] function name`, `export [default] class Name`
- `export const name = (...) =>`, `= async x =>`, `= function`
- `module.exports = function`, `module.exports.name = ...`, `exports.name = ...`

Not found: `export { a, b }`, `module.exports = { a, b }`, and values wrapped
in a call, like `export const Button = memo(...)`.

An export is documented when the comment right above it (decorators aside)
is a /** ... */ block. A // comment, or a blank line in between, doesn't
count: editors only show JSDoc.
"""

import re

IDENTIFIER = r"[A-Za-z_$][\w$]*"
FUNCTION_VALUE = rf"(?:async\s+)?(?:function\b|\(|{IDENTIFIER}\s*=>)"
NAME = rf"(?P<name>{IDENTIFIER})"

EXPORTS = [
    re.compile(
        r"\s*export\s+(?:default\s+)?(?:async\s+)?function\b\s*\*?\s*" + NAME + "?"
    ),
    re.compile(r"\s*export\s+(?:default\s+)?(?:abstract\s+)?class\b\s*" + NAME + "?"),
    re.compile(
        rf"\s*export\s+(?:const|let|var)\s+{NAME}\s*(?::[^=]+)?=\s*{FUNCTION_VALUE}"
    ),
    re.compile(rf"\s*module\.exports(?:\.{NAME})?\s*=\s*(?:{FUNCTION_VALUE}|class\b)"),
    re.compile(rf"\s*exports\.{NAME}\s*=\s*(?:{FUNCTION_VALUE}|class\b)"),
]
DEFAULT = "default"  # an anonymous default export, or `module.exports = ...`


def js_names(text: str) -> list[tuple[str, bool]]:
    """(name, has JSDoc) for each exported function or class, in file order."""
    lines = text.splitlines()
    merged: dict[str, bool] = {}
    for number, line in enumerate(lines):
        name = exported_name(line)
        if name is not None:
            # TypeScript overloads repeat a name: documented if any one is.
            merged[name] = merged.get(name, False) or has_jsdoc_above(lines, number)
    return list(merged.items())


def exported_name(line: str) -> str | None:
    for pattern in EXPORTS:
        match = pattern.match(line)
        if match is not None:
            return match["name"] or DEFAULT
    return None


def has_jsdoc_above(lines: list[str], number: int) -> bool:
    """True if the line above `number` (skipping @decorators) ends a /** block."""
    above = number - 1
    while above >= 0 and lines[above].lstrip().startswith("@"):
        above -= 1
    if above < 0 or not lines[above].rstrip().endswith("*/"):
        return False
    while above >= 0 and "/*" not in lines[above]:
        above -= 1  # walk up to where the comment starts
    return above >= 0 and "/**" in lines[above]
