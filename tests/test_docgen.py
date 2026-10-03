import re
from pathlib import PurePosixPath

import pytest
from conftest import FAKE_SECRETS

from devai.docgen import plan as plan_module
from devai.docgen.js_insert import format_jsdoc, is_one_comment, js_targets
from devai.docgen.lines import (
    WIDTH,
    Target,
    clean_text,
    insert_blocks,
    split_lines,
    wrap_text,
)
from devai.docgen.plan import DocsError, plan_docs
from devai.docgen.python_insert import (
    format_docstring,
    python_code_unchanged,
    python_targets,
)
from devai.docmap.python_docs import MODULE, NotPython, python_names

PY = PurePosixPath("stats.py")
JS = PurePosixPath("search.js")


def targets_of(targets):
    return [(t.name, t.line, t.indent, t.inline, t.blank_after) for t in targets]


# --- lines and text -------------------------------------------------------------------


def test_lines_split_only_where_python_does():
    assert split_lines("a\r\nb\rc\nd") == ["a\r\n", "b\r", "c\n", "d"]
    assert split_lines("page\x0cbreak\n") == ["page\x0cbreak\n"]  # a form feed
    assert split_lines("") == []


def test_clean_text():
    text = "\n\n  Summary.\t\x1b[31m \n\n\n\nDetails.  \r\nMore.\n\n"

    assert clean_text(text) == "  Summary.     [31m\n\nDetails.\nMore."


def test_long_lines_are_wrapped_keeping_their_indent():
    long = "word " * 20

    assert wrap_text("Short.", 30) == ["Short."]
    assert all(len(line) <= 30 for line in wrap_text(long, 30))
    assert wrap_text("  " + long, 30)[1].startswith("  word")
    assert wrap_text("@param {string} query " + long, 30)[1].startswith("  word")
    url = "https://example.com/" + "x" * 40
    assert wrap_text(f"See {url}", 30) == ["See", url]  # never broken


def test_blocks_keep_the_files_line_endings():
    text = "a\r\nb\r\nc\r\n"
    blocks = [(Target("x", 2, ""), ["X"]), (Target("y", 1, ""), ["Y1", "Y2"])]

    assert insert_blocks(text, blocks) == "a\r\nY1\r\nY2\r\nb\r\nX\r\nc\r\n"


# --- where Python docstrings go -------------------------------------------------------

PYTHON = """\
#!/usr/bin/env python3
# A comment before the code.
import os


@decorator
def run(
    a,
    b,
):  # a comment on the header
    # a comment that opens the body
    return a + b


class Cart:
    def add(self, item):
        self.items.append(item)

    @property
    def size(self):
        return 1

    @size.setter
    def size(self, value):
        pass

    def _check(self):
        pass


def inline(): pass


def documented():
    \"\"\"Already here.\"\"\"
"""


def test_python_targets():
    assert targets_of(python_targets(PYTHON)) == [
        (MODULE, 2, "", False, True),  # before `import os`, after the comments
        ("run", 10, "    ", False, False),  # after the header's `):`
        ("Cart", 15, "    ", False, True),
        ("Cart.add", 16, "        ", False, False),
        ("Cart.size", 20, "        ", False, False),  # the first definition
        ("inline", 30, "", True, False),
    ]


def test_python_targets_match_what_devai_docs_reports():
    reported = [name for name, documented in python_names(PYTHON) if not documented]

    assert [target.name for target in python_targets(PYTHON)] == reported


def test_a_setter_with_docs_documents_the_property():
    code = (
        "class Box:\n"
        '    """A box."""\n'
        "    @property\n"
        "    def size(self):\n"
        "        return 1\n"
        "    @size.setter\n"
        "    def size(self, value):\n"
        '        """Set the size."""\n'
    )

    assert [t.name for t in python_targets('"""Doc."""\n' + code)] == []


def test_an_inline_body_after_a_long_signature():
    code = '"""Doc."""\ndef f(\n    a,\n): return a\n'

    assert targets_of(python_targets(code)) == [("f", 3, "", True, False)]


def test_an_empty_module_has_no_targets():
    assert python_targets("") == []
    assert python_targets("# just a comment\n") == []


def test_invalid_python_raises():
    with pytest.raises(NotPython):
        python_targets("def broken(:\n")


# --- docstring and JSDoc formatting ---------------------------------------------------


def test_short_docstrings_fit_on_one_line():
    assert format_docstring("Add two numbers.", "    ") == [
        '    """Add two numbers."""'
    ]


def test_longer_docstrings_put_the_quotes_on_their_own_line():
    lines = format_docstring("Add two numbers.\n\nReturns the sum.", "    ")

    assert lines == [
        '    """Add two numbers.',
        "",  # a blank line has no trailing spaces
        "    Returns the sum.",
        '    """',
    ]


def test_long_docstring_lines_are_wrapped():
    lines = format_docstring("Return " + "the value " * 20, "        ")

    assert len(lines) > 2
    assert all(len(line) <= WIDTH for line in lines)


def test_a_backslash_makes_a_raw_docstring():
    assert format_docstring(r"Split at \n.", "") == ['r"""Split at \\n."""']


def test_a_final_quote_moves_the_closing_quotes_to_their_own_line():
    assert format_docstring('Return "x"', "") == ['"""Return "x"', '"""']


def test_jsdoc_formatting():
    assert format_jsdoc("Search the index.", "") == ["/** Search the index. */"]
    assert format_jsdoc("Search.\n\n@param {string} query", "  ") == [
        "  /**",
        "   * Search.",
        "   *",
        "   * @param {string} query",
        "   */",
    ]
    assert all(len(line) <= WIDTH for line in format_jsdoc("word " * 40, ""))


def test_one_comment_and_nothing_else():
    assert is_one_comment(["/** Doc. */"])
    assert is_one_comment(["/**", " * Doc.", " */"])
    assert not is_one_comment(["/** Doc. */ run();"])
    assert not is_one_comment(["/** a */", "/** b */"])
    assert not is_one_comment(["// Doc."])


# --- where JSDoc goes -----------------------------------------------------------------

JAVASCRIPT = """\
import x from "y";

@Component({})
@Other()
export class Widget {}

  export function indented() {}

/** Already documented. */
export function documented() {}

export function overloaded(a: string): void;
export function overloaded(a: number): void;
"""


def test_js_targets():
    assert targets_of(js_targets(JAVASCRIPT)) == [
        ("Widget", 2, "", False, False),  # above the decorators
        ("indented", 6, "  ", False, False),
        ("overloaded", 11, "", False, False),  # above the first one
    ]


# --- the proof for Python -------------------------------------------------------------


def test_only_docstrings_differ():
    before = "def f(a):\n    return a + 1\n"
    after = 'def f(a):\n    """Add one."""\n    return a + 1\n'

    assert python_code_unchanged(before, after) is True


def test_any_code_change_fails_the_proof():
    before = "def f(a):\n    return a + 1\n"
    after = 'def f(a):\n    """Add one."""\n    return a + 2\n'

    assert python_code_unchanged(before, after) is False


def test_invalid_python_after_raises():
    with pytest.raises(SyntaxError):
        python_code_unchanged("x = 1\n", 'x = 1\n"""\n')


# --- planning a change ----------------------------------------------------------------

STATS = (
    "def average(values):\n"
    "    return sum(values) / len(values)\n"
    "\n"
    "\n"
    "class Box:\n"
    "    def size(self):\n"
    "        return 1\n"
)
ASKED = ["(module)", "average", "Box", "Box.size"]


def test_a_python_plan():
    docs = [
        ("(module)", "Statistics helpers."),
        ("average", "Return the mean.\n\nRaises ZeroDivisionError if empty."),
        ("Box", "A box."),
        ("Box.size", "The size."),
    ]

    plan = plan_docs(PY, STATS, docs, ASKED)

    assert plan.added == ("(module)", "average", "Box", "Box.size")
    assert plan.dropped == ()
    assert plan.change.after == (
        '"""Statistics helpers."""\n'
        "\n"
        "def average(values):\n"
        '    """Return the mean.\n'
        "\n"
        "    Raises ZeroDivisionError if empty.\n"
        '    """\n'
        "    return sum(values) / len(values)\n"
        "\n"
        "\n"
        "class Box:\n"
        '    """A box."""\n'
        "\n"
        "    def size(self):\n"
        '        """The size."""\n'
        "        return 1\n"
    )
    assert plan.change.diff.startswith("--- a/stats.py\n+++ b/stats.py\n")
    assert plan.change.before == STATS


def test_a_javascript_plan():
    code = "export function search(index, query) {\n  return [];\n}\n"

    plan = plan_docs(JS, code, [("search", "Search the index.")], ["search"])

    assert plan.change.after == "/** Search the index. */\n" + code


def test_crlf_files_stay_crlf():
    code = STATS.replace("\n", "\r\n")

    plan = plan_docs(PY, code, [("average", "Return the mean.")], ASKED)

    assert '    """Return the mean."""\r\n' in plan.change.after
    assert "\n" not in plan.change.after.replace("\r\n", "")


def test_names_devai_did_not_ask_about_are_dropped():
    docs = [
        ("average", "Return the mean."),
        ("median", "Not in the file."),
        ("Box", "Not asked."),
        ("average", "Again."),
        ("Box.size", "   \n "),
    ]

    plan = plan_docs(PY, STATS, docs, ["average", "Box.size"])

    assert plan.added == ("average",)
    assert plan.dropped == (
        ("median", "not one of the names DevAI asked about"),
        ("Box", "not one of the names DevAI asked about"),
        ("average", "listed twice; the first text was used"),
        ("Box.size", "no text"),
    )


def test_an_inline_body_is_dropped():
    code = '"""Doc."""\ndef f(): pass\n'

    plan = plan_docs(PY, code, [("f", "Do nothing.")], ["f"])

    assert plan.change is None
    assert plan.dropped == (("f", "its body is on the definition's line"),)


def test_a_text_that_is_too_long_is_dropped():
    plan = plan_docs(PY, STATS, [("average", "line\n" * 25)], ASKED)

    assert plan.change is None
    assert plan.dropped == (("average", "too long (at most 20 lines)"),)


def test_quotes_and_comment_markers_the_ai_added_are_removed():
    python = plan_docs(PY, STATS, [("average", '"""Return the mean."""')], ASKED)
    js = plan_docs(
        JS,
        "export function f() {}\n",
        [("f", "/**\n * Do it.\n * @returns {void}\n */")],
        ["f"],
    )

    assert '    """Return the mean."""\n' in python.change.after
    assert js.change.after.startswith("/**\n * Do it.\n * @returns {void}\n */\n")


@pytest.mark.parametrize(
    ("path", "text", "reason"),
    [
        # Text that would close the docstring or comment and slip code in.
        (PY, 'Mean."""\nimport os; os.system("x")\n"""', 'contain """'),
        (JS, 'Search. */ fetch("https://evil.example") /*', "contain */"),
        (PY, "Uses [redacted: possible secret] to log in.", "hidden as a possible"),
        (
            PY,
            "Default key: " + FAKE_SECRETS["secret/github-token"][0],
            "possible secret",
        ),
    ],
)
def test_unsafe_text_rejects_the_whole_proposal(path, text, reason):
    code = (
        STATS if path == PY else "export function average() {}\nexport class Box {}\n"
    )
    # A fine entry first: one unsafe entry still rejects everything.
    docs = [("average", "Return the mean."), ("Box", text)]

    with pytest.raises(DocsError, match=re.escape(reason)):
        plan_docs(path, code, docs, ["average", "Box"])


def test_nothing_usable_means_no_change():
    plan = plan_docs(PY, STATS, [], ASKED)

    assert plan.change is None
    assert plan.added == ()


# --- the proof catches a placement bug ------------------------------------------------


def test_a_code_change_from_a_placement_bug_is_rejected(monkeypatch):
    def buggy(text, blocks):
        return insert_blocks(text, blocks).replace("len(values)", "len(values) + 1")

    monkeypatch.setattr(plan_module, "insert_blocks", buggy)

    with pytest.raises(DocsError, match="would change the code"):
        plan_docs(PY, STATS, [("average", "Return the mean.")], ASKED)


def test_a_docstring_in_the_wrong_place_is_rejected(monkeypatch):
    def misplaced(text, blocks):
        # The docstring lands after the code: valid Python, not a docstring.
        return text + "".join(line + "\n" for _, block in blocks for line in block)

    monkeypatch.setattr(plan_module, "insert_blocks", misplaced)

    with pytest.raises(DocsError):
        plan_docs(PY, STATS, [("average", "Return the mean.")], ASKED)


def test_jsdoc_in_the_wrong_place_is_rejected(monkeypatch):
    code = "const a = 1;\nexport function f() {}\n"

    def at_the_top(text, blocks):
        return "".join(line + "\n" for _, block in blocks for line in block) + text

    monkeypatch.setattr(plan_module, "insert_blocks", at_the_top)

    with pytest.raises(DocsError, match="not be where docs belong"):
        plan_docs(JS, code, [("f", "Do it.")], ["f"])


def test_a_jsdoc_block_with_code_is_rejected(monkeypatch):
    monkeypatch.setattr(
        plan_module, "format_jsdoc", lambda text, indent: ["/** Doc. */ run();"]
    )

    with pytest.raises(DocsError, match="single comment"):
        plan_docs(JS, "export function f() {}\n", [("f", "Doc.")], ["f"])
