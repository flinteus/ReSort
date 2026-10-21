from fastapi.security import HTTPBearer
from typing import Generator
from sqlalchemy.orm import Session

from app.db.database import SessionLocal

security = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        
    finally:
        db.close()
    