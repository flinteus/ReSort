from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    width: int
    height: int
    size_bytes: int
    created_at: datetime
