from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, unique=True, nullable=False, index=True)
    
    full_name = Column(String, nullable=True)
    car_number = Column(String, nullable=True)
    
    approved = Column(Boolean, default=False)
    banned = Column(Boolean, default=False)
    role = Column(String, default="driver")

    shifts = relationship("Shift", back_populates="user")


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.tg_id"), nullable=False)
    
    date = Column(Date, nullable=False)
    start_time = Column(DateTime, default=datetime.utcnow)

    start_km = Column(Integer, nullable=False)
    start_fuel = Column(Float, nullable=False)
    end_km = Column(Integer)
    end_fuel = Column(Float)
    refueled_liters = Column(Float, default=0.0)
    calculated_consumption = Column(Float)
    distance = Column(Integer)
    consumed_liters = Column(Float)
    car_number = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="shifts")
