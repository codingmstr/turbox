from sqlalchemy import Column, String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Otp(Base):

    __tablename__ = "otps"

    id          = Column(Integer, primary_key=True, index=True)
    agent_id    = Column(Integer, primary_key=True, index=True)
    is_verified = Column(Boolean, default=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
