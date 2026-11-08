from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

class RecognitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    item_name: str = Field(min_length=1, max_length=200)
    category_code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    material_code: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    needs_clarification: bool = Field(strict=True)
    clarification_question: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_clarification(self):
        if self.needs_clarification and not self.clarification_question:
            raise ValueError("clarification_question is required when needs_clarification is true")
        if not self.needs_clarification and self.clarification_question is not None:
            raise ValueError("clarification_question requires needs_clarification=true")
        return self


class SortingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recognition: RecognitionResult
    region_code: str = Field(default="general", min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")


class Source(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: HttpUrl


class GuidanceImport(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category_code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    material_code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    material_name: str = Field(min_length=1, max_length=200)
    region_code: str = Field(default="general", min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    preparation_steps: list[str] = Field(min_length=1, max_length=30)
    restrictions: list[str] = Field(max_length=30)
    environmental_impact: str = Field(min_length=1, max_length=5000)
    sources: list[Source] = Field(min_length=1, max_length=20)
    reviewed_by: str = Field(min_length=1, max_length=200)
    reviewed_at: date

    @model_validator(mode="after")
    def validate_review(self):
        if self.reviewed_at > date.today():
            raise ValueError("reviewed_at must not be in the future")
        if any(not text.strip() or len(text) > 2000 for text in self.preparation_steps + self.restrictions):
            raise ValueError("steps and restrictions must be nonempty and at most 2000 characters")
        return self


class GuidanceResponse(BaseModel):
    material_code: str
    material_name: str
    category_code: str
    region_code: str
    preparation_steps: list[str]
    restrictions: list[str]
    environmental_impact: str
    sources: list[Source]
    reviewed_at: date


class SortingResponse(BaseModel):
    status: Literal["ready", "needs_clarification", "rules_not_available"]
    recognition: RecognitionResult
    clarification_question: str | None = None
    guidance: GuidanceResponse | None = None


class MaterialResponse(BaseModel):
    material_code: str
    material_name: str
    category_code: str
    region_code: str
