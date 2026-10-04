"""Comments DevAI may post on GitHub, and how (D053).

A comment is posted only after the user has read its exact text and typed
"y" in a terminal (or confirmed in the web page); --yes never posts. Before
that, the text is made safe for a public page:

- "@name" and "#12" are broken with an invisible character, so a comment
  never notifies people or links itself into other issues;
- it never holds code from the diff or a secret: local findings carry only
  masked evidence, and a line that still looks like a secret refuses it;
- it says it was written with AI, by which model, and is capped in length.
"""

import re
from pathlib import Path

from devai.ai.result import AIResult
from devai.checks.secrets import match_line
from devai.github.gh import GitHubError, run_gh
from devai.models import ReviewReport

MAX_COMMENT_CHARACTERS = 60_000  # GitHub accepts 65,536
INVISIBLE = "⁠"  # word joiner: "@⁠name" shows as @name, mentions no one
# "@name" (not in emails), and "#12" anywhere, "owner/repo#12" included.
MENTION = re.compile(r"(?<![\w`])@(?=[\w-])|#(?=\d)")
REDACTION_MARKER = "[redacted"
SEVERITY_ICONS = {"high": "🔴", "medium": "🟠", "low": "🔵"}


class CommentError(Exception):
    """The comment can't be posted as it is. The message is safe to show."""


def neutralize(text: str) -> str:
    """Break @mentions and #references; keep the text readable."""
    return MENTION.sub(lambda match: match[0] + INVISIBLE, text)


def pull_comment(report: ReviewReport, ai: AIResult | None, discarded: int = 0) -> str:
    """The review of a pull request, as Markdown for one comment."""
    lines = ["### DevAI review", ""]
    findings = report.checks.findings
    lines.append("**Local checks** (deterministic, no AI):")
    if findings:
        for finding in findings:
            where = f" `{finding.file}`" if finding.file else ""
            evidence = f" ({finding.evidence})" if finding.evidence else ""
            icon = SEVERITY_ICONS.get(finding.severity, "")
            severity = finding.severity.upper()
            lines.append(f"- {icon} **{severity}** {finding.message}{where}{evidence}")
    else:
        lines.append("- No findings.")
    if ai is not None:
        review = ai.report
        lines += ["", f"**AI review** ({ai.model}):", "", review.summary]
        for issue in review.issues:
            where = f"`{issue.file}:{issue.line}`" if issue.line else f"`{issue.file}`"
            icon = SEVERITY_ICONS.get(issue.severity, "")
            lines.append(
                f"- {icon} **{issue.severity.upper()}** {where} {issue.title}: "
                f"{issue.explanation} *Suggestion:* {issue.suggestion}"
            )
        if not review.issues:
            lines.append("- No issues found.")
        if review.suggested_tests:
            lines += ["", "Suggested tests:"]
            lines += [f"- {test}" for test in review.suggested_tests]
        if discarded:
            note = (
                f"_{discarded} issue(s) about code the AI wasn't shown were discarded._"
            )
            lines += ["", note]
    lines += ["", footer(ai)]
    return finish(lines)


def issue_comment(plan: AIResult) -> str:
    """An AI plan for an issue, as Markdown for one comment."""
    report = plan.report
    lines = ["### DevAI plan", "", report.summary]
    if report.files:
        lines += ["", "**Files to look at:**"]
        lines += [f"- `{file.path}`: {file.why}" for file in report.files]
    if report.steps:
        lines += ["", "**Steps:**"]
        lines += [f"{number}. {step}" for number, step in enumerate(report.steps, 1)]
    if report.tests:
        lines += ["", "**Tests:**"]
        lines += [f"- {test}" for test in report.tests]
    if report.questions:
        lines += ["", "**Open questions:**"]
        lines += [f"- {question}" for question in report.questions]
    lines += ["", footer(plan)]
    return finish(lines)


def footer(ai: AIResult | None) -> str:
    if ai is None:
        return "<sub>Posted with DevAI after its user read it. Local checks only.</sub>"
    return (
        f"<sub>Written with a free AI model ({ai.model}) through DevAI, and posted "
        "after its user read it. AI can be wrong: verify before acting.</sub>"
    )


def finish(lines: list[str]) -> str:
    """Neutralize, check and cap the comment."""
    text = neutralize("\n".join(lines).strip())
    for line in text.split("\n"):
        if REDACTION_MARKER in line:
            raise CommentError(
                "the comment includes a line hidden as a possible secret"
            )
        finding = match_line(line)
        if finding is not None:
            raise CommentError(
                f"the comment includes a possible secret ({finding.message})"
            )
    if len(text) > MAX_COMMENT_CHARACTERS:
        cut = "\n\n_(cut: too long for one comment)_"
        text = text[: MAX_COMMENT_CHARACTERS - len(cut)] + cut
    return text


def post(root: Path, kind: str, repo: str, number: int, body: str) -> str:
    """Post `body` on pull request or issue `number` of `repo`. Returns its URL.

    Only callers that showed `body` and got the user's yes may call this.
    """
    if kind not in ("pr", "issue"):
        raise GitHubError(f"unknown kind {kind!r}")
    output = run_gh(
        [kind, "comment", str(number), "--repo", repo, "--body-file", "-"],
        root,
        stdin=body,
    )
    return output.strip().splitlines()[-1] if output.strip() else ""
