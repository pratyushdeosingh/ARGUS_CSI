"""Prototype investigation workflow and draft reporting. No regulatory filing."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ConfigDict, Field, model_validator

from .models import StrictModel
from .storage import ArgusStore, get_argus_store


router = APIRouter(prefix="/api/incidents", tags=["Investigations"])


class InvestigationUpdate(StrictModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    actor: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=0)
    assigned_to: str | None = Field(default=None, min_length=1, max_length=100)
    status: Literal["open", "investigating", "escalated", "closed"] | None = None
    note: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set.intersection({"assigned_to", "status", "note"}):
            raise ValueError("Provide assignment, investigation status or a note")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("Investigation status cannot be null")
        if "note" in self.model_fields_set and self.note is None:
            raise ValueError("A note cannot be null")
        return self


@router.get("/{incident_id}/investigation")
def get_investigation(incident_id: str, store: ArgusStore = Depends(get_argus_store)):
    try:
        return store.get_investigation(incident_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Incident not found") from error


@router.patch("/{incident_id}/investigation")
def update_investigation(incident_id: str, update: InvestigationUpdate,
                         store: ArgusStore = Depends(get_argus_store)):
    changes = update.model_dump(exclude_unset=True, exclude={"actor", "expected_revision"})
    try:
        return store.update_investigation(incident_id, update.actor, update.expected_revision, changes)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Incident not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{incident_id}/report")
def draft_report(incident_id: str, store: ArgusStore = Depends(get_argus_store)):
    try:
        snapshot = store.report_snapshot(incident_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Incident not found") from error
    return {
        "report_type": "draft_suspicious_activity_report",
        "schema_version": "draft-report.v1",
        "status": "DRAFT_NOT_FILED",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notice": "Synthetic prototype investigation summary. Not a regulatory filing or compliance determination. Human review required.",
        "actor_identity": "Caller-supplied prototype identities; no authenticated identity assurance",
        **snapshot,
    }
