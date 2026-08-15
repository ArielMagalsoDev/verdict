from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class LeadAccepted(BaseModel):
    lead_id: UUID
    job_id: UUID
    status: str = "processing"
    status_url: str
    replayed: bool = False


class DraftDecisionIn(BaseModel):
    action: Literal["approve", "reject"]
    edited_body: str | None = None
