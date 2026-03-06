from sqlalchemy.orm import Session
import models, schemas

# USERS
def create_user(db: Session, user: schemas.UserCreate):
    db_user = models.User(username=user.username, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_users(db: Session):
    return db.query(models.User).all()

# EVENTS
def create_event(db: Session, event: schemas.EventCreate):
    db_event = models.Event(**event.dict(), available_tickets=event.total_tickets)
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event

def get_events(db: Session):
    return db.query(models.Event).all()

def update_event(db: Session, event_id: int, event_update: schemas.EventUpdate):
    db_event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if db_event:
        for key, value in event_update.dict(exclude_unset=True).items():
            setattr(db_event, key, value)
        db.commit()
        db.refresh(db_event)
    return db_event

# BOOKINGS (Glavna logika)
def create_booking(db: Session, booking: schemas.BookingCreate):
    # 1. Provjeri postoji li event i ima li karata
    event = db.query(models.Event).filter(models.Event.id == booking.event_id).first()
    if not event or event.available_tickets <= 0:
        return None
    
    # 2. Smanji broj karata
    event.available_tickets -= 1
    
    # 3. Kreiraj rezervaciju
    db_booking = models.Booking(user_id=booking.user_id, event_id=booking.event_id)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking

def delete_booking(db: Session, booking_id: int):
    db_booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if db_booking:
        # Vrati kartu eventu
        event = db.query(models.Event).filter(models.Event.id == db_booking.event_id).first()
        event.available_tickets += 1
        db.delete(db_booking)
        db.commit()
        return True
    return False