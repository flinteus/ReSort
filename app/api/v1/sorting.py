from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.v1.auth import Database, current_session
from app.models.sorting import SortingGuidance
from app.models.user import AuthSession
from app.schemas.sorting import GuidanceResponse, MaterialResponse, SortingRequest, SortingResponse

router = APIRouter(tags=["sorting"])
Authenticated = Annotated[AuthSession, Depends(current_session)]


@router.get("/waste/materials", response_model=list[MaterialResponse])
def materials(
    db: Database,
    session: Authenticated,
    region_code: Annotated[str, Query(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")] = "general",
):
    return db.scalars(select(SortingGuidance).where(SortingGuidance.region_code == region_code)
                      .order_by(SortingGuidance.material_code)).all()


@router.post("/sorting/recommendation", response_model=SortingResponse)
def recommendation(body: SortingRequest, db: Database, session: Authenticated):
    recognition = body.recognition
    if recognition.needs_clarification or recognition.material_code is None:
        return SortingResponse(status="needs_clarification", recognition=recognition,
                               clarification_question=recognition.clarification_question or
                               "Уточните материал или пришлите фотографию маркировки.")
    guidance = db.scalar(select(SortingGuidance).where(
        SortingGuidance.material_code == recognition.material_code,
        SortingGuidance.region_code == body.region_code,
    ))
    if guidance is None:
        return SortingResponse(status="rules_not_available", recognition=recognition)
    if guidance.category_code != recognition.category_code:
        raise HTTPException(status_code=422, detail="Material does not belong to the supplied category")
    return SortingResponse(status="ready", recognition=recognition,
                           guidance=GuidanceResponse.model_validate(guidance, from_attributes=True))
