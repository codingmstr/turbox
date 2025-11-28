from sqlalchemy import Column, String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Token(Base):

    __tablename__ = "tokens"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, index=True)
    is_active   = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
