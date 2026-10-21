from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

class User(Base):
    
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[int] = mapped_column(unique=True)
