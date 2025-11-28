from sqlalchemy import Column, String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Agent(Base):

    __tablename__ = "agents"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(150), nullable=False)
    phone       = Column(String(150), nullable=False)
    email       = Column(String(150), unique=True, index=True, nullable=False)
    password    = Column(String(255), nullable=False)
    is_verified = Column(Boolean, default=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
