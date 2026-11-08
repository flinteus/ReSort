import hashlib
import json
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, select

from app.api.v1.auth import Database, current_session
from app.core.security import utcnow
from app.models.collection_point import CollectionPoint, CollectionPointMaterial
from app.models.photo import Photo
from app.models.progress import Achievement, SortingEvent
from app.models.sorting import SortingGuidance
from app.models.user import AuthSession, User
from app.schemas.progress import (AchievementResponse, SortingConfirmation, SortingConfirmationResponse,
                                  SortingEventList, SortingEventResponse, TreeResponse, UserAchievementResponse)
from app.services.progress import award_achievements, earned_achievements, tree

router = APIRouter(tags=["sorting-progress"])
Authenticated = Annotated[AuthSession, Depends(current_session)]


def confirmation_response(db, event):
    return SortingConfirmationResponse(event=SortingEventResponse.model_validate(event),
                                       awarded_achievements=earned_achievements(db, event.user_id, event.id),
                                       tree=tree(db, event.user_id))


@router.post("/sorting-events", response_model=SortingConfirmationResponse, status_code=201)
def confirm_sorting(body: SortingConfirmation, response: Response, db: Database, session: Authenticated,
                    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")]):
    user_id = session.user_id
    fingerprint = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True,
                                            separators=(",", ":")).encode()).hexdigest()
    # All confirmations for a user are serialized, including duplicate retries and awards.
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    existing = db.scalar(select(SortingEvent).where(SortingEvent.user_id == user_id,
                                                   SortingEvent.idempotency_key == str(idempotency_key)))
    if existing:
        if existing.request_hash != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key already used for a different request")
        response.status_code = 200
        return confirmation_response(db, existing)
    photo = db.scalar(select(Photo).where(Photo.id == str(body.photo_id), Photo.user_id == user_id).with_for_update())
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if db.scalar(select(SortingEvent.id).where(SortingEvent.photo_reference == str(body.photo_id))):
        raise HTTPException(status_code=409, detail="Sorting already confirmed for this photo")
    guidance = db.scalar(select(SortingGuidance).where(SortingGuidance.material_code == body.material_code,
                                                       SortingGuidance.region_code == body.region_code))
    if guidance is None:
        raise HTTPException(status_code=422, detail="Unknown material/region")
    point = None
    if body.collection_point_id is not None:
        point = db.scalar(select(CollectionPoint).where(CollectionPoint.id == str(body.collection_point_id),
                                                        CollectionPoint.is_active.is_(True)).with_for_update())
        if point is None:
            raise HTTPException(status_code=404, detail="Collection point not found")
        if not db.get(CollectionPointMaterial, (point.id, body.material_code, body.region_code)):
            raise HTTPException(status_code=422, detail="Collection point does not accept this material/region")
    event = SortingEvent(id=str(uuid4()), user_id=user_id, photo_id=photo.id, photo_reference=photo.id,
                         material_code=guidance.material_code, region_code=guidance.region_code,
                         material_name=guidance.material_name, category_code=guidance.category_code,
                         collection_point_id=point.id if point else None,
                         collection_point_name=point.name if point else None,
                         idempotency_key=str(idempotency_key), request_hash=fingerprint, created_at=utcnow())
    try:
        db.add(event)
        db.flush()
        award_achievements(db, event)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return confirmation_response(db, event)


@router.get("/sorting-events", response_model=SortingEventList)
def sorting_events(db: Database, session: Authenticated,
                   limit: Annotated[int, Query(ge=1, le=100)] = 20,
                   offset: Annotated[int, Query(ge=0, le=10000)] = 0):
    filters = [SortingEvent.user_id == session.user_id]
    items = db.scalars(select(SortingEvent).where(*filters).order_by(SortingEvent.created_at.desc(), SortingEvent.id)
                       .limit(limit).offset(offset)).all()
    total = db.scalar(select(func.count()).select_from(SortingEvent).where(*filters))
    return SortingEventList(items=[SortingEventResponse.model_validate(e) for e in items], total=total)


@router.get("/sorting-events/{event_id}", response_model=SortingEventResponse)
def sorting_event(event_id: UUID, db: Database, session: Authenticated):
    event = db.scalar(select(SortingEvent).where(SortingEvent.id == str(event_id), SortingEvent.user_id == session.user_id))
    if event is None:
        raise HTTPException(status_code=404, detail="Sorting event not found")
    return event


@router.get("/achievements", response_model=list[AchievementResponse])
def achievements(db: Database):
    return db.scalars(select(Achievement).order_by(Achievement.metric, Achievement.target, Achievement.code)).all()


@router.get("/users/me/achievements", response_model=list[UserAchievementResponse])
def user_achievements(db: Database, session: Authenticated):
    return earned_achievements(db, session.user_id)


@router.get("/users/me/tree", response_model=TreeResponse)
def user_tree(db: Database, session: Authenticated):
    return tree(db, session.user_id)
