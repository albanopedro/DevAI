"""The structure an AI test proposal must have (validated by Pydantic).

Named GeneratedTests, not TestProposal: pytest tries to collect any class
whose name starts with "Test".
"""

from pydantic import BaseModel, Field


class GeneratedTests(BaseModel):
    path: str = Field(
        description="Project-relative path of the NEW test file; it must not exist"
    )
    content: str = Field(description="The full content of the new test file")
    covers: list[str] = Field(description="Functions, classes or behaviors tested")
    notes: list[str] = Field(
        description="Assumptions and what the developer should check before running"
    )
