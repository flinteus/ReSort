from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class AcceptedMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    material_code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    region_code: str = Field(default="general", min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    notes: str = Field(default="", max_length=2000)


class CollectionPointImport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    source_code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    external_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=500)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    opening_hours: str = Field(min_length=1, max_length=1000)
    timezone: str = Field(max_length=100)
    website: HttpUrl | None = None
    notes: str = Field(default="", max_length=3000)
    is_active: bool = Field(default=True, strict=True)
    source_url: HttpUrl = Field(max_length=2000)
    reviewed_at: date
    reviewed_by: str = Field(min_length=1, max_length=200)
    accepted_materials: list[AcceptedMaterial] = Field(min_length=1, max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Expected an IANA timezone") from None
        return value

    @field_validator("website")
    @classmethod
    def website_length(cls, value):
        if value is not None and len(str(value)) > 2000:
            raise ValueError("website exceeds 2000 characters")
        return value

    @model_validator(mode="after")
    def validate_record(self):
        if self.reviewed_at > date.today():
            raise ValueError("reviewed_at must not be in the future")
        keys = [(m.material_code, m.region_code) for m in self.accepted_materials]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate accepted material/region")
        return self


class AcceptedMaterialResponse(AcceptedMaterial):
    category_code: str
    material_name: str


class CollectionPointResponse(BaseModel):
    id: UUID
    name: str
    city: str
    address: str
    latitude: float
    longitude: float
    opening_hours: str
    timezone: str
    website: HttpUrl | None
    notes: str
    source_url: HttpUrl
    reviewed_at: date
    accepted_materials: list[AcceptedMaterialResponse]
    distance_m: float | None = None


class CollectionPointList(BaseModel):
    items: list[CollectionPointResponse]
    total: int
