from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

import app.models as models, app.schemas as schemas, app.crud as crud
from app.database import engine, get_db


models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Event Booking API",
    description="API za rezervaciju karata - Diplomski projekt (Performance Testing)",
    version="1.0.0",
)


@app.post("/users/", response_model=schemas.User, tags=["Users"])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    return crud.create_user(db=db, user=user)


@app.get("/users/", response_model=List[schemas.User], tags=["Users"])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Dohvaća listu korisnika uz podršku za paginaciju."""
    return crud.get_users(db, skip=skip, limit=limit)


@app.get("/users/{user_id}", response_model=schemas.User, tags=["Users"])
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@app.delete("/users/{user_id}", tags=["Users"])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """Briše korisnika i sve njegove povezane rezervacije."""
    success = crud.delete_user(db, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User and their bookings deleted successfully"}


@app.get(
    "/users/{user_id}/bookings", response_model=List[schemas.Booking], tags=["Users"]
)
def read_user_bookings(user_id: int, db: Session = Depends(get_db)):
    return crud.get_user_bookings(db, user_id=user_id)


@app.post("/events/", response_model=schemas.Event, tags=["Events"])
def create_event(event: schemas.EventCreate, db: Session = Depends(get_db)):
    return crud.create_event(db=db, event=event)


@app.get("/events/", response_model=List[schemas.Event], tags=["Events"])
def read_events(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Dohvaća listu događaja uz podršku za paginaciju."""
    return crud.get_events(db, skip=skip, limit=limit)


@app.get("/events/{event_id}", response_model=schemas.Event, tags=["Events"])
def read_event(event_id: int, db: Session = Depends(get_db)):
    db_event = crud.get_event(db, event_id=event_id)
    if db_event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return db_event


@app.put("/events/{event_id}", response_model=schemas.Event, tags=["Events"])
def update_event(
    event_id: int, event: schemas.EventUpdate, db: Session = Depends(get_db)
):
    db_event = crud.update_event(db=db, event_id=event_id, event_update=event)
    if db_event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return db_event


@app.delete("/events/{event_id}", tags=["Events"])
def delete_event(event_id: int, db: Session = Depends(get_db)):
    """Briše događaj i sve rezervacije vezane uz njega."""
    success = crud.delete_event(db, event_id=event_id)
    if not success:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"message": "Event and its bookings deleted successfully"}


@app.post("/bookings/", response_model=schemas.Booking, tags=["Bookings"])
def create_booking(booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    db_booking = crud.create_booking(db=db, booking=booking)
    if db_booking is None:
        raise HTTPException(
            status_code=400,
            detail="Rezervacija neuspješna: Provjerite ID korisnika/događaja ili dostupnost karata.",
        )
    return db_booking


@app.get("/bookings/", response_model=List[schemas.Booking], tags=["Bookings"])
def read_bookings(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Dohvaća listu svih rezervacija uz podršku za paginaciju."""
    return crud.get
