from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    pass


class User(UserBase):
    id: int

    class Config:
        from_attributes = True


class EventBase(BaseModel):
    title: str
    location: str
    total_tickets: int


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    total_tickets: Optional[int] = None


class Event(EventBase):
    id: int
    available_tickets: int

    class Config:
        from_attributes = True


class BookingCreate(BaseModel):
    user_id: int
    event_id: int


class Booking(BaseModel):
    id: int
    user_id: int
    event_id: int
    timestamp: datetime

    class Config:
        from_attributes = True
