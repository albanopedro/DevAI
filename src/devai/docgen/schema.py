"""The structure a documentation proposal must have (validated by Pydantic)."""

from pydantic import BaseModel, Field


class DocText(BaseModel):
    name: str = Field(description="One of the names to document, exactly as given")
    text: str = Field(
        description="The documentation only: plain text, without quotes, comment "
        "markers or indentation"
    )


class DocsProposal(BaseModel):
    docs: list[DocText] = Field(
        description="One entry per name you can describe from the code"
    )
    notes: list[str] = Field(
        description="Assumptions, and names you skipped with the reason"
    )
