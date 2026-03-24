from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="user", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    location = Column(String, index=True)
    date = Column(DateTime, index=True)
    price = Column(Float, default=0.0)
    total_tickets = Column(Integer)
    available_tickets = Column(Integer)

    bookings = relationship("Booking", back_populates="event", cascade="all, delete-orphan")


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    event_id = Column(Integer, ForeignKey("events.id"), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="confirmed", index=True)

    user = relationship("User", back_populates="bookings")
    event = relationship("Event", back_populates="bookings")
