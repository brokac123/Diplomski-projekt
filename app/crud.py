from sqlalchemy.orm import Session
import app.models as models, app.schemas as schemas


def create_user(db: Session, user: schemas.UserCreate):
    db_user = models.User(username=user.username, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_users(db: Session):
    return db.query(models.User).all()


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def update_user(db: Session, user_id: int, user_update: schemas.UserCreate):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db_user.username = user_update.username
        db_user.email = user_update.email
        db.commit()
        db.refresh(db_user)
    return db_user


def create_event(db: Session, event: schemas.EventCreate):
    # Prilikom kreiranja, available_tickets je jednako total_tickets
    db_event = models.Event(**event.dict(), available_tickets=event.total_tickets)
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


def get_events(db: Session):
    return db.query(models.Event).all()


def get_event(db: Session, event_id: int):
    return db.query(models.Event).filter(models.Event.id == event_id).first()


def update_event(db: Session, event_id: int, event_update: schemas.EventUpdate):
    db_event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if db_event:
        # exclude_unset=True osigurava da ne pregazimo polja koja nismo poslali u PUT zahtjevu
        for key, value in event_update.dict(exclude_unset=True).items():
            setattr(db_event, key, value)
        db.commit()
        db.refresh(db_event)
    return db_event


def create_booking(db: Session, booking: schemas.BookingCreate):
    # 1. Provjeri postoji li event i ima li dovoljno slobodnih karata
    event = db.query(models.Event).filter(models.Event.id == booking.event_id).first()
    if not event or event.available_tickets <= 0:
        return None

    # 2. Provjeri postoji li uopće taj korisnik
    user = db.query(models.User).filter(models.User.id == booking.user_id).first()
    if not user:
        return None

    # 3. Smanji broj dostupnih karata za event
    event.available_tickets -= 1

    # 4. Kreiraj zapis o rezervaciji
    db_booking = models.Booking(user_id=booking.user_id, event_id=booking.event_id)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking


def get_bookings(db: Session):
    return db.query(models.Booking).all()


def get_user_bookings(db: Session, user_id: int):
    return db.query(models.Booking).filter(models.Booking.user_id == user_id).all()


def delete_booking(db: Session, booking_id: int):
    db_booking = (
        db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    )
    if db_booking:
        # Prije brisanja rezervacije, vratimo kartu u "bazen" slobodnih karata
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
