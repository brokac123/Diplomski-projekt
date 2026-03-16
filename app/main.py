from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app import models, schemas, crud
from app.database import SessionLocal, engine
from prometheus_fastapi_instrumentator import Instrumentator


models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Booking API - Verzija 1")


Instrumentator().instrument(app).expose(app)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- USERS ---


@app.get("/users/", response_model=List[schemas.User], tags=["Users"])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
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


@app.get(
    "/users/{user_id}/bookings", response_model=List[schemas.Booking], tags=["Users"]
)
def get_user_bookings(user_id: int, db: Session = Depends(get_db)):
    bookings = crud.get_bookings_by_user(db, user_id)
    return bookings


# --- EVENTS ---


@app.get("/events/", response_model=List[schemas.Event], tags=["Events"])
def read_events(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_events(db, skip=skip, limit=limit)


@app.get("/events/{event_id}", response_model=schemas.Event, tags=["Events"])
def read_event(event_id: int, db: Session = Depends(get_db)):
    db_event = crud.get_event(db, event_id=event_id)
    if db_event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return db_event


@app.post("/events/", response_model=schemas.Event, tags=["Events"])
def create_event(event: schemas.EventCreate, db: Session = Depends(get_db)):
    return crud.create_event(db=db, event=event)


@app.delete("/events/{event_id}", tags=["Events"])
def delete_event(event_id: int, db: Session = Depends(get_db)):
    if not crud.delete_event(db, event_id):
        raise HTTPException(status_code=404, detail="Event not found")
    return {"message": f"Event {event_id} deleted"}


@app.put("/events/{event_id}", response_model=schemas.Event, tags=["Events"])
def update_event(
    event_id: int, event: schemas.EventCreate, db: Session = Depends(get_db)
):
    db_event = crud.update_event(db, event_id, event)
    if db_event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return db_event


@app.patch("/events/{event_id}", response_model=schemas.Event, tags=["Events"])
def patch_event(
    event_id: int, event: schemas.EventUpdate, db: Session = Depends(get_db)
):
    db_event = crud.patch_event(db, event_id, event)
    if db_event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return db_event


@app.get(
    "/events/{event_id}/bookings", response_model=List[schemas.Booking], tags=["Events"]
)
def get_event_bookings(event_id: int, db: Session = Depends(get_db)):
    bookings = crud.get_bookings_by_event(db, event_id)
    return bookings


# --- BOOKINGS ---


@app.get("/bookings/", response_model=List[schemas.Booking], tags=["Bookings"])
def read_bookings(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_bookings(db, skip=skip, limit=limit)


@app.post("/bookings/", response_model=schemas.Booking, tags=["Bookings"])
def create_booking(booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    db_booking = crud.create_booking(db=db, booking=booking)
    if db_booking is None:
        raise HTTPException(
            status_code=400, detail="Booking failed: No tickets or invalid IDs"
        )
    return db_booking


@app.delete("/bookings/{booking_id}", tags=["Bookings"])
def delete_booking(booking_id: int, db: Session = Depends(get_db)):
    if not crud.delete_booking(db, booking_id=booking_id):
        raise HTTPException(status_code=404, detail="Booking not found")
    return {"message": "Booking deleted and ticket returned"}


@app.get("/bookings/{booking_id}", response_model=schemas.Booking, tags=["Bookings"])
def read_booking(booking_id: int, db: Session = Depends(get_db)):
    booking = crud.get_booking(db, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking
