from pathlib import PurePosixPath

import pytest
from conftest import FAKE_SECRETS, fake_fix_proposal

from devai.fix.edits import MAX_CHANGED_LINES, FixError, apply_edits
from devai.fix.schema import FixEdit

STATS = PurePosixPath("stats.py")
ORIGINAL = (
    "def average(values):\n"
    "    return sum(values) / len(values)\n"
    "\n"
    "\n"
    "def percent(part, whole):\n"
    "    return part / whole * 100\n"
)


def edit(old, new, file="stats.py"):
    return FixEdit(file=file, old_text=old, new_text=new, reason="r")


def propose(*edits, originals=None):
    return apply_edits(
        fake_fix_proposal(edits=list(edits)), originals or {STATS: ORIGINAL}
    )


# --- a valid proposal ----------------------------------------------------------------


def test_valid_proposal_is_applied_in_memory_with_a_diff():
    [change] = apply_edits(fake_fix_proposal(), {STATS: ORIGINAL})

    assert change.path == STATS
    assert change.before == ORIGINAL
    assert '        raise ValueError("whole must not be zero")\n' in change.after
    assert change.diff.startswith("--- a/stats.py\n+++ b/stats.py\n@@ ")
    assert "+    if whole == 0:\n" in change.diff


def test_edits_on_the_same_file_apply_in_order():
    [change] = propose(
        edit("return sum(values)", "return float(sum(values))"),
        edit("return float(sum(values))", "return sum(values) * 1.0"),
    )

    assert "return sum(values) * 1.0 / len(values)" in change.after


def test_no_edits_means_no_changes():
    assert apply_edits(fake_fix_proposal(edits=[]), {STATS: ORIGINAL}) == []


def test_crlf_files_keep_their_line_endings():
    crlf = ORIGINAL.replace("\n", "\r\n")

    [change] = propose(
        edit("    return part / whole * 100", "    return 100 * part / whole"),
        originals={STATS: crlf},
    )

    assert "    return 100 * part / whole\r\n" in change.after
    assert "\n" not in change.after.replace("\r\n", "")


def test_leading_dot_slash_in_the_path_is_accepted():
    assert propose(edit("* 100", "* 100.0", file="./stats.py"))


# --- every rule rejects the whole proposal --------------------------------------------


@pytest.mark.parametrize(
    ("proposed", "message"),
    [
        (edit("x", "y", file="other.py"), "wasn't named with --file"),
        (edit("not in the file", "y"), "text not found in stats.py"),
        (edit("return", "give back"), "appears 2 times"),
        (edit("", "y"), "doesn't say which text"),
        (edit("* 100", "* 100  # [redacted: possible secret (AKIA…)]"), "hidden as a"),
        (edit("[redacted: possible secret (AKIA…)]", "y"), "hidden as a"),
        (edit("    return part / whole * 100", "    return part /"), "valid Python"),
    ],
)
def test_rules(proposed, message):
    with pytest.raises(FixError, match=message):
        propose(proposed)


def test_a_new_secret_is_rejected():
    secret, _ = FAKE_SECRETS["secret/github-token"]

    with pytest.raises(FixError, match="would add a possible secret"):
        propose(edit("* 100", f"* 100  # token {secret}"))


def test_invalid_json_is_rejected():
    config = PurePosixPath("config.json")

    with pytest.raises(FixError, match="valid JSON"):
        apply_edits(
            fake_fix_proposal(
                edits=[edit('"debug": false', '"debug": ', "config.json")]
            ),
            {config: '{"debug": false}\n'},
        )


def test_too_large_a_change_is_rejected():
    big = "".join(f"x_{n} = {n}\n" for n in range(MAX_CHANGED_LINES + 1))

    with pytest.raises(FixError, match="too large"):
        propose(edit("    return part / whole * 100\n", f"    return 0\n{big}"))


def test_too_many_edits_are_rejected():
    edits = [edit("* 100", "* 100") for _ in range(11)]

    with pytest.raises(FixError, match="too many edits"):
        propose(*edits)
