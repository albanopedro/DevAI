"""The structure the model must answer with (validated by Pydantic, D006)."""

from typing import Literal

from pydantic import BaseModel, Field


class AIRisk(BaseModel):
    title: str = Field(description="Short name of the risk")
    severity: Literal["high", "medium", "low"]
    explanation: str = Field(description="Why it matters, based on the summary")
    related_rule: str | None = Field(
        description="rule_id of the finding this risk comes from, or null"
    )


class AIRecommendation(BaseModel):
    title: str = Field(description="A concrete next step")
    rationale: str = Field(description="Why this step, based on the summary")
    effort: Literal["small", "medium", "large"]


class AIReport(BaseModel):
    summary: str = Field(description="2-4 sentences: what the project is, its stack")
    risks: list[AIRisk]
    recommendations: list[AIRecommendation] = Field(
        description="Most valuable first, at most 5"
    )
    limitations: list[str] = Field(
        description="What could not be assessed from the summary"
    )
