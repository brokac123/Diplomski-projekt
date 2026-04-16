from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app import models, schemas, crud
from app.database import engine, get_db
from prometheus_fastapi_instrumentator import Instrumentator


models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Booking API - Verzija 1")

Instrumentator().instrument(app).expose(app)


# --- HEALTH ---

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


# --- USERS ---

@app.get("/users/", response_model=List[schemas.User], tags=["Users"])
def read_users(skip: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)):
    return crud.get_users(db, skip=skip, limit=limit)


@app.get("/users/{user_id}", response_model=schemas.User, tags=["Users"])
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@app.post("/users/", response_model=schemas.User, tags=["Users"])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    return crud.create_user(db=db, user=user)


@app.delete("/users/{user_id}", tags=["Users"])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    if not crud.delete_user(db, user_id=user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User {user_id} deleted"}


@app.put("/users/{user_id}", response_model=schemas.User, tags=["Users"])
def update_user(user_id: int, user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.update_user(db, user_id, user)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@app.patch("/users/{user_id}", response_model=schemas.User, tags=["Users"])
def patch_user(user_id: int, user: schemas.UserUpdate, db: Session = Depends(get_db)):
    db_user = crud.patch_user(db, user_id, user)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@app.get("/users/{user_id}/bookings", response_model=List[schemas.Booking], tags=["Users"])
def get_user_bookings(user_id: int, skip: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)):
    return crud.get_bookings_by_user(db, user_id, skip=skip, limit=limit)


# --- EVENTS ---

@app.get("/events/", response_model=List[schemas.Event], tags=["Events"])
def read_events(skip: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)):
    return crud.get_events(db, skip=skip, limit=limit)


@app.get("/events/upcoming", response_model=List[schemas.Event], tags=["Events"])
def get_upcoming_events(skip: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)):
    return crud.get_upcoming_events(db, skip=skip, limit=limit)


@app.get("/events/search", response_model=List[schemas.Event], tags=["Events"])
def search_events(
    location: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    return crud.search_events(db, location=location, date_from=date_from, date_to=date_to, skip=skip, limit=limit)


@app.get("/events/popular", response_model=List[schemas.PopularEvent], tags=["Events"])
def get_popular_events(limit: int = Query(default=10, ge=1, le=100), db: Session = Depends(get_db)):
    return crud.get_popular_events(db, limit=limit)


@app.get("/events/{event_id}", response_model=schemas.Event, tags=["Events"])
def read_event(event_id: int, db: Session = Depends(get_db)):
    db_event = crud.get_event(db, event_id=event_id)
    if db_event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return db_event


@app.get("/events/{event_id}/stats", response_model=schemas.EventStats, tags=["Events"])
def get_event_stats(event_id: int, db: Session = Depends(get_db)):
    stats = crud.get_event_stats(db, event_id=event_id)
    if stats is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return stats


@app.get("/events/{event_id}/bookings", response_model=List[schemas.Booking], tags=["Events"])
def get_event_bookings(event_id: int, skip: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)):
    return crud.get_bookings_by_event(db, event_id, skip=skip, limit=limit)


@app.post("/events/", response_model=schemas.Event, tags=["Events"])
def create_event(event: schemas.EventCreate, db: Session = Depends(get_db)):
    return crud.create_event(db=db, event=event)


@app.delete("/events/{event_id}", tags=["Events"])
def delete_event(event_id: int, db: Session = Depends(get_db)):
    if not crud.delete_event(db, event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    return {"message": f"Event {event_id} deleted"}


@app.put("/events/{event_id}", response_model=schemas.Event, tags=["Events"])
def update_event(event_id: int, event: schemas.EventCreate, db: Session = Depends(get_db)):
    db_event, reason = crud.update_event(db, event_id, event)
    if reason == "not_found":
        raise HTTPException(status_code=404, detail="Event not found")
    if reason == "invalid":
        raise HTTPException(status_code=400, detail="total_tickets cannot be less than already booked tickets")
    return db_event


@app.patch("/events/{event_id}", response_model=schemas.Event, tags=["Events"])
def patch_event(event_id: int, event: schemas.EventUpdate, db: Session = Depends(get_db)):
    db_event, reason = crud.patch_event(db, event_id, event)
    if reason == "not_found":
        raise HTTPException(status_code=404, detail="Event not found")
    if reason == "invalid":
        raise HTTPException(status_code=400, detail="total_tickets cannot be less than already booked tickets")
    return db_event


# --- BOOKINGS ---

@app.get("/bookings/", response_model=List[schemas.Booking], tags=["Bookings"])
def read_bookings(skip: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=1000), db: Session = Depends(get_db)):
    return crud.get_bookings(db, skip=skip, limit=limit)


@app.get("/bookings/{booking_id}", response_model=schemas.Booking, tags=["Bookings"])
def read_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = crud.get_booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


@app.post("/bookings/", response_model=schemas.Booking, tags=["Bookings"])
def create_booking(booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    db_booking, reason = crud.create_booking(db=db, booking=booking)
    if reason == "event_not_found":
        raise HTTPException(status_code=404, detail="Event not found")
    if reason == "user_not_found":
        raise HTTPException(status_code=404, detail="User not found")
    if reason == "sold_out":
        raise HTTPException(status_code=409, detail="No tickets available for this event")
    return db_booking


@app.patch("/bookings/{booking_id}/cancel", response_model=schemas.Booking, tags=["Bookings"])
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    db_booking, reason = crud.cancel_booking(db=db, booking_id=booking_id)
    if reason == "not_found":
        raise HTTPException(status_code=404, detail="Booking not found")
    if reason == "already_cancelled":
        raise HTTPException(status_code=409, detail="Booking is already cancelled")
    return db_booking


@app.delete("/bookings/{booking_id}", tags=["Bookings"])
def delete_booking(booking_id: int, db: Session = Depends(get_db)):
    if not crud.delete_booking(db, booking_id=booking_id):
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"message": "Booking deleted and ticket returned"}


# --- STATS ---

@app.get("/stats", response_model=schemas.GlobalStats, tags=["Stats"])
def get_global_stats(db: Session = Depends(get_db)):
    return crud.get_global_stats(db)
