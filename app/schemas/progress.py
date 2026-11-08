from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SortingConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    photo_id: UUID
    material_code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    region_code: str = Field(default="general", min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    collection_point_id: UUID | None = None
    confirmed: bool = Field(strict=True)

    @field_validator("confirmed")
    @classmethod
    def must_confirm(cls, value):
        if not value:
            raise ValueError("Explicit sorting confirmation is required")
        return value


class SortingEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    photo_id: UUID | None
    material_code: str
    region_code: str
    material_name: str
    category_code: str
    collection_point_id: UUID | None
    collection_point_name: str | None
    created_at: datetime


class AchievementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str
    metric: Literal["sorting_count", "distinct_materials"]
    target: int


class UserAchievementResponse(AchievementResponse):
    earned_at: datetime


class TreeResponse(BaseModel):
    stage: Literal["seed", "sprout", "sapling", "young_tree", "mature_tree"]
    stage_name: str
    level: int
    sorting_count: int
    distinct_materials: int
    unlocked_achievements: int
    next_stage_at: int | None
    progress_current: int
    progress_required: int | None
    progress_percent: int


class SortingConfirmationResponse(BaseModel):
    event: SortingEventResponse
    awarded_achievements: list[UserAchievementResponse]
    tree: TreeResponse


class SortingEventList(BaseModel):
    items: list[SortingEventResponse]
    total: int
