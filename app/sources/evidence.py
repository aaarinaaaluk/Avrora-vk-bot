"""Общая модель доказательного фрагмента из разрешённого источника."""

from pydantic import BaseModel, Field


class EvidenceRecord(BaseModel):
    evidence_id: str
    source_id: str
    source_name: str
    source_url: str
    excerpt: str
    source_type: str
    published_at: str | None = None
    limitations: list[str] = Field(default_factory=list)
    page_number: int | None = None
