from sqlalchemy.orm import Session
import app.models as models, app.schemas as schemas


def create_user(db: Session, user: schemas.UserCreate):
    db_user = models.User(username=user.username, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def delete_user(db: Session, user_id: int):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        # Prvo brišemo sve njegove rezervacije (ili pustimo DB da odradi CASCADE)
        db.query(models.Booking).filter(models.Booking.user_id == user_id).delete()
        db.delete(db_user)
        db.commit()
        return True
    return False


def create_event(db: Session, event: schemas.EventCreate):
    db_event = models.Event(**event.dict(), available_tickets=event.total_tickets)
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


def get_events(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Event).offset(skip).limit(limit).all()


def get_event(db: Session, event_id: int):
    return db.query(models.Event).filter(models.Event.id == event_id).first()


def delete_event(db: Session, event_id: int):
    db_event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if db_event:
        # Brišemo i sve rezervacije vezane uz ovaj event
        db.query(models.Booking).filter(models.Booking.event_id == event_id).delete()
        db.delete(db_event)
        db.commit()
        return True
    return False


def create_booking(db: Session, booking: schemas.BookingCreate):
    # (Zadržavamo tvoju logiku za sada kako bismo je mogli testirati)
    event = db.query(models.Event).filter(models.Event.id == booking.event_id).first()
    if not event or event.available_tickets <= 0:
        return None

    user = db.query(models.User).filter(models.User.id == booking.user_id).first()
    if not user:
        return None

    event.available_tickets -= 1
    db_booking = models.Booking(user_id=booking.user_id, event_id=booking.event_id)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking


def get_bookings(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Booking).offset(skip).limit(limit).all()


def delete_booking(db: Session, booking_id: int):
    db_booking = (
        db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    )
    if db_booking:
        event = (
            db.query(models.Event)
            .filter(models.Event.id == db_booking.event_id)
            .first()
        )
        if event:
            event.available_tickets += 1
        db.delete(db_booking)
        db.commit()
        return True
    return False
