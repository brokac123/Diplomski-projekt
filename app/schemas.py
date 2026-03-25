from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime


# --- USER ---

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
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- EVENT ---

class EventBase(BaseModel):
    title: str
    location: str
    date: datetime
    price: float
    total_tickets: int


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    date: Optional[datetime] = None
    price: Optional[float] = None
    total_tickets: Optional[int] = None


class Event(EventBase):
    id: int
    available_tickets: int

    model_config = ConfigDict(from_attributes=True)


# --- BOOKING ---

class BookingBase(BaseModel):
    event_id: int
    user_id: int


class BookingCreate(BookingBase):
    pass


class Booking(BookingBase):
    id: int
    timestamp: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)


# --- RESPONSE SCHEMAS FOR HEAVY ENDPOINTS ---

class EventStats(BaseModel):
    event_id: int
    title: str
    total_tickets: int
    available_tickets: int
    booked_tickets: int
    occupancy_pct: float
    total_revenue: float
    cancelled_bookings: int


class PopularEvent(BaseModel):
    event_id: int
    title: str
    location: str
    date: datetime
    price: float
    confirmed_bookings: int


class GlobalStats(BaseModel):
    total_users: int
    total_events: int
    total_bookings: int
    confirmed_bookings: int
    cancelled_bookings: int
    total_revenue: float
    avg_occupancy_pct: float
    new_users_last_30_days: int
