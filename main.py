from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import models, schemas, crud
from database import engine, get_db

# Kreiraj tablice automatski
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Event Booking API")

# USERS
@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    return crud.create_user(db=db, user=user)

@app.get("/users/", response_model=List[schemas.User])
def read_users(db: Session = Depends(get_db)):
    return crud.get_users(db)

# EVENTS
@app.post("/events/", response_model=schemas.Event)
def create_event(event: schemas.EventCreate, db: Session = Depends(get_db)):
    return crud.create_event(db=db, event=event)

@app.get("/events/", response_model=List[schemas.Event])
def read_events(db: Session = Depends(get_db)):
    return crud.get_events(db)

@app.put("/events/{event_id}", response_model=schemas.Event)
def update_event(event_id: int, event: schemas.EventUpdate, db: Session = Depends(get_db)):
    return crud.update_event(db=db, event_id=event_id, event_update=event)

# BOOKINGS
@app.post("/bookings/", response_model=schemas.Booking)
def create_booking(booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    db_booking = crud.create_booking(db=db, booking=booking)
    if db_booking is None:
        raise HTTPException(status_code=400, detail="No tickets available or event not found")
    return db_booking

@app.delete("/bookings/{booking_id}")
def delete_booking(booking_id: int, db: Session = Depends(get_db)):
    success = crud.delete_booking(db=db, booking_id=booking_id)
    if not success:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"message": "Booking cancelled successfully"}