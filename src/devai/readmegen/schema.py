"""The structure a README proposal must have (validated by Pydantic)."""

from pydantic import BaseModel, Field


class ReadmeSection(BaseModel):
    topic: str = Field(description="One of the topics asked for, exactly as given")
    heading: str = Field(
        description="The section title in the README's language, without # marks"
    )
    body: str = Field(description="The section content in Markdown, without its title")


class ReadmeProposal(BaseModel):
    description: str = Field(
        description="Only when there is no README: 1 to 3 sentences on what the "
        "project is. Otherwise empty"
    )
    sections: list[ReadmeSection] = Field(description="One section per topic")
    notes: list[str] = Field(description="Assumptions, and topics you skipped and why")
