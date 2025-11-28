from sqlalchemy import Column, String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):

    __tablename__ = "users"

    id          = Column(Integer, primary_key=True, index=True)
    first_name  = Column(String(100), nullable=False)
    last_name   = Column(String(100), nullable=False)
    email       = Column(String(150), unique=True, index=True, nullable=False)
    phone       = Column(String(20), unique=True, nullable=True)
    password    = Column(String(255), nullable=False)
    is_active   = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
