from sqlalchemy import Column, String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Provider(Base):

    __tablename__ = "providers"

    id          = Column(Integer, primary_key=True, index=True)
    first_name  = Column(String(100), nullable=False)
    last_name   = Column(String(100), nullable=False)
    email       = Column(String(150), unique=True, index=True, nullable=False)
    phone       = Column(String(20), unique=True, nullable=True)
