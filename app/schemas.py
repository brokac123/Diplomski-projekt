from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime


class BaseConfig:
    from_attributes = True


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None


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
    available_tickets: Optional[int] = None


class Event(EventBase):
    id: int
    available_tickets: int

    class Config:
        from_attributes = True


class BookingBase(BaseModel):
    event_id: int
    user_id: int


class BookingCreate(BookingBase):
    pass


class Booking(BookingBase):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True
