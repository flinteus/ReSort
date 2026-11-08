import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.v1.auth import Database
from app.models.collection_point import CollectionPoint, CollectionPointMaterial
from app.models.sorting import SortingGuidance
from app.schemas.collection_point import AcceptedMaterialResponse, CollectionPointList, CollectionPointResponse

router = APIRouter(prefix="/collection-points", tags=["collection-points"])
EARTH_RADIUS_M = 6371008.8
CodeQuery = Annotated[str | None, Query(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")]


def serialize_point(point: CollectionPoint, distance: float | None = None):
    return CollectionPointResponse(
        id=point.id, name=point.name, city=point.city, address=point.address,
        latitude=point.latitude, longitude=point.longitude,
        opening_hours=point.opening_hours, timezone=point.timezone, website=point.website,
        notes=point.notes, source_url=point.source_url, reviewed_at=point.reviewed_at,
        accepted_materials=[AcceptedMaterialResponse(
            material_code=m.material_code, region_code=m.region_code, notes=m.notes,
            category_code=m.guidance.category_code, material_name=m.guidance.material_name,
        ) for m in point.materials],
        distance_m=round(distance, 1) if distance is not None else None,
    )


@router.get("", response_model=CollectionPointList)
def collection_points(
    db: Database,
    lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
    radius_m: Annotated[int, Query(ge=1, le=100000)] = 5000,
    material_code: CodeQuery = None,
    category_code: CodeQuery = None,
    region_code: CodeQuery = None,
    city: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
):
    if (lat is None) != (lon is None):
        raise HTTPException(status_code=422, detail="lat and lon must be supplied together")
    filters = [CollectionPoint.is_active.is_(True)]
    if city is not None:
        filters.append(func.lower(CollectionPoint.city) == city.strip().lower())
    if any(value is not None for value in (material_code, category_code, region_code)):
        accepted = select(CollectionPointMaterial.point_id).join(SortingGuidance).where(
            CollectionPointMaterial.point_id == CollectionPoint.id)
        if material_code is not None:
            accepted = accepted.where(CollectionPointMaterial.material_code == material_code)
        if category_code is not None:
            accepted = accepted.where(SortingGuidance.category_code == category_code)
        if region_code is not None:
            accepted = accepted.where(CollectionPointMaterial.region_code == region_code)
        filters.append(accepted.exists())
    distance = None
    if lat is not None:
        delta = math.degrees(radius_m / EARTH_RADIUS_M)
        filters.append(CollectionPoint.latitude.between(max(-90, lat - delta), min(90, lat + delta)))
        a = func.power(func.sin(func.radians(CollectionPoint.latitude - lat) / 2), 2) + (
            math.cos(math.radians(lat)) * func.cos(func.radians(CollectionPoint.latitude)) *
            func.power(func.sin(func.radians(CollectionPoint.longitude - lon) / 2), 2))
        distance = 2 * EARTH_RADIUS_M * func.asin(func.sqrt(func.least(1.0, func.greatest(0.0, a))))
        filters.append(distance <= radius_m)
    total = db.scalar(select(func.count()).select_from(CollectionPoint).where(*filters))
    if distance is None:
        points = db.scalars(select(CollectionPoint).where(*filters).order_by(
            CollectionPoint.name, CollectionPoint.id).limit(limit).offset(offset)).all()
        items = [serialize_point(p) for p in points]
    else:
        rows = db.execute(select(CollectionPoint, distance.label("distance_m")).where(*filters)
                          .order_by(distance, CollectionPoint.id).limit(limit).offset(offset)).all()
        items = [serialize_point(p, d) for p, d in rows]
    return CollectionPointList(items=items, total=total)


@router.get("/{point_id}", response_model=CollectionPointResponse)
def collection_point(point_id: UUID, db: Database):
    point = db.scalar(select(CollectionPoint).where(CollectionPoint.id == str(point_id),
                                                  CollectionPoint.is_active.is_(True)))
    if point is None:
        raise HTTPException(status_code=404, detail="Collection point not found")
    return serialize_point(point)
