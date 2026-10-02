"""The structure a chat answer must have (validated by Pydantic)."""

from pydantic import BaseModel, Field


class SuggestedFile(BaseModel):
    path: str = Field(description="Project-relative path of a file you would need")
    reason: str = Field(description="Why it would help answer the question")


class ChatAnswer(BaseModel):
    answer: str = Field(description="The answer, based on the shown files and summary")
    sources: list[str] = Field(
        description='"path:line" references you relied on, from the shown files'
    )
    suggested_files: list[SuggestedFile] = Field(
        description="Up to 3 other project files you would need; empty if none"
    )
