"""The structure an issue plan must have (validated by Pydantic)."""

from pydantic import BaseModel, Field


class PlanFile(BaseModel):
    path: str = Field(description="A project file from the package, exactly as given")
    why: str = Field(description="What in it relates to the issue")


class IssuePlan(BaseModel):
    summary: str = Field(description="The problem or request, in 1-3 sentences")
    files: list[PlanFile] = Field(
        description="Files from the package likely to change; empty if none were sent"
    )
    steps: list[str] = Field(description="Concrete steps to resolve it, in order")
    tests: list[str] = Field(description="Tests that would show it is resolved")
    questions: list[str] = Field(
        description="What is unclear and should be asked to the issue's author"
    )
