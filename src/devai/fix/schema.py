"""The structure a fix proposal must have (validated by Pydantic)."""

from pydantic import BaseModel, Field


class FixEdit(BaseModel):
    file: str = Field(description="One of the files you may change, exactly as given")
    old_text: str = Field(
        description="Exact current text to replace, copied from the file; it must "
        "appear exactly once in that file"
    )
    new_text: str = Field(description="The text that replaces old_text")
    reason: str = Field(description="Why this edit")


class FixProposal(BaseModel):
    summary: str = Field(description="What the fix does, in 1-3 sentences")
    edits: list[FixEdit] = Field(
        description="The smallest set of edits; empty if no change is needed"
    )
    risks: list[str] = Field(description="What the change could break")
    tests: list[str] = Field(description="How to verify the fix")
