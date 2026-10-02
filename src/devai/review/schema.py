"""The structure an AI code review must answer with (validated by Pydantic)."""

from typing import Literal

from pydantic import BaseModel, Field


class ReviewIssue(BaseModel):
    file: str = Field(description="Changed file path, exactly as in the review context")
    line: int | None = Field(
        description="Line number in the NEW version of the file, or null"
    )
    severity: Literal["high", "medium", "low"]
    category: Literal[
        "bug", "security", "performance", "maintainability", "tests", "style"
    ]
    title: str = Field(description="Short name of the issue")
    explanation: str = Field(
        description="What is wrong and why, based on the shown code"
    )
    suggestion: str = Field(description="A concrete fix")


class AIReviewReport(BaseModel):
    summary: str = Field(description="2-4 sentences: what the change does")
    issues: list[ReviewIssue] = Field(
        description="Most important first; empty if the change looks fine"
    )
    suggested_tests: list[str] = Field(description="Tests this change should have")
    limitations: list[str] = Field(
        description="What could not be judged from the hunks alone"
    )
