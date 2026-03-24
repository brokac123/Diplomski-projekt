from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
import app.models as models
import app.schemas as schemas


# --- USER CRUD ---

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()


def create_user(db: Session, user: schemas.UserCreate):
    db_user = models.User(username=user.username, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: int):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db.delete(db_user)  # cascade handles bookings
        db.commit()
        return True
    return False


def update_user(db: Session, user_id: int, user: schemas.UserCreate):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        return None
    db_user.username = user.username
    db_user.email = user.email
    db.commit()
    db.refresh(db_user)
    return db_user


def patch_user(db: Session, user_id: int, user: schemas.UserUpdate):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        return None
    for key, value in user.dict(exclude_unset=True).items():
        setattr(db_user, key, value)
    db.commit()
    db.refresh(db_user)
    return db_user


# --- EVENT CRUD ---

def get_event(db: Session, event_id: int):
    return db.query(models.Event).filter(models.Event.id == event_id).first()


def get_events(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Event).offset(skip).limit(limit).all()


def create_event(db: Session, event: schemas.EventCreate):
    db_event = models.Event(**event.dict(), available_tickets=event.total_tickets)
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


def delete_event(db: Session, event_id: int):
    db_event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if db_event:
        db.delete(db_event)  # cascade handles bookings
        db.commit()
        return True
    return False


def update_event(db: Session, event_id: int, event: schemas.EventCreate):
    db_event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not db_event:
        return None, "not_found"

    booked_tickets = db_event.total_tickets - db_event.available_tickets
    if event.total_tickets < booked_tickets:
        return None, "invalid"

    db_event.title = event.title
    db_event.location = event.location
    db_event.date = event.date
    db_event.price = event.price
    db_event.total_tickets = event.total_tickets
    db_event.available_tickets = event.total_tickets - booked_tickets
    db.commit()
    db.refresh(db_event)
    return db_event, "ok"


def patch_event(db: Session, event_id: int, event: schemas.EventUpdate):
    db_event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not db_event:
        return None
    for key, value in event.dict(exclude_unset=True).items():
        setattr(db_event, key, value)
    db.commit()
    db.refresh(db_event)
    return db_event


def get_upcoming_events(db: Session, skip: int = 0, limit: int = 100):
    return (
        db.query(models.Event)
        .filter(models.Event.date > datetime.utcnow())
        .order_by(models.Event.date.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def search_events(db: Session, location: str = None, date_from: datetime = None, date_to: datetime = None, skip: int = 0, limit: int = 100):
    query = db.query(models.Event)
    if location:
        query = query.filter(models.Event.location == location)
    if date_from:
        query = query.filter(models.Event.date >= date_from)
    if date_to:
        query = query.filter(models.Event.date <= date_to)
    return query.order_by(models.Event.date.asc()).offset(skip).limit(limit).all()


def get_event_stats(db: Session, event_id: int):
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        return None

    confirmed = (
        db.query(func.count(models.Booking.id))
        .filter(models.Booking.event_id == event_id, models.Booking.status == "confirmed")
        .scalar()
    )
    cancelled = (
        db.query(func.count(models.Booking.id))
        .filter(models.Booking.event_id == event_id, models.Booking.status == "cancelled")
        .scalar()
    )
    booked = event.total_tickets - event.available_tickets
    occupancy = round((booked / event.total_tickets * 100), 2) if event.total_tickets > 0 else 0.0
    revenue = round(confirmed * event.price, 2)

    return schemas.EventStats(
        event_id=event.id,
        title=event.title,
        total_tickets=event.total_tickets,
        available_tickets=event.available_tickets,
        booked_tickets=booked,
        occupancy_pct=occupancy,
        total_revenue=revenue,
        cancelled_bookings=cancelled,
    )


def get_popular_events(db: Session, limit: int = 10):
    results = (
        db.query(
            models.Event,
            func.count(models.Booking.id).label("confirmed_bookings"),
        )
        .join(models.Booking, models.Booking.event_id == models.Event.id)
        .filter(models.Booking.status == "confirmed")
        .group_by(models.Event.id)
        .order_by(func.count(models.Booking.id).desc())
        .limit(limit)
        .all()
    )
    return [
        schemas.PopularEvent(
            event_id=event.id,
            title=event.title,
            location=event.location,
            date=event.date,
            price=event.price,
            confirmed_bookings=count,
        )
        for event, count in results
    ]


def get_global_stats(db: Session):
    total_users = db.query(func.count(models.User.id)).scalar()
    total_events = db.query(func.count(models.Event.id)).scalar()
    total_bookings = db.query(func.count(models.Booking.id)).scalar()
    confirmed = (
        db.query(func.count(models.Booking.id))
        .filter(models.Booking.status == "confirmed")
        .scalar()
    )
    cancelled = (
        db.query(func.count(models.Booking.id))
        .filter(models.Booking.status == "cancelled")
        .scalar()
    )
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    new_users = (
        db.query(func.count(models.User.id))
        .filter(models.User.created_at >= thirty_days_ago)
        .scalar()
    )

    # average occupancy across all events
    events = db.query(models.Event).all()
    if events:
        avg_occupancy = round(
            sum(
                (e.total_tickets - e.available_tickets) / e.total_tickets * 100
                for e in events if e.total_tickets > 0
            ) / len(events),
            2,
        )
    else:
        avg_occupancy = 0.0

    # total revenue from confirmed bookings
    revenue_result = (
        db.query(func.sum(models.Event.price))
        .join(models.Booking, models.Booking.event_id == models.Event.id)
        .filter(models.Booking.status == "confirmed")
        .scalar()
    )
    total_revenue = round(revenue_result or 0.0, 2)

    return schemas.GlobalStats(
        total_users=total_users,
        total_events=total_events,
        total_bookings=total_bookings,
        confirmed_bookings=confirmed,
        cancelled_bookings=cancelled,
        total_revenue=total_revenue,
        avg_occupancy_pct=avg_occupancy,
        new_users_last_30_days=new_users,
    )


# --- BOOKING CRUD ---

def get_bookings(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Booking).offset(skip).limit(limit).all()


def get_booking(db: Session, booking_id: int):
    return db.query(models.Booking).filter(models.Booking.id == booking_id).first()


def get_bookings_by_user(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    return (
        db.query(models.Booking)
        .filter(models.Booking.user_id == user_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_bookings_by_event(db: Session, event_id: int, skip: int = 0, limit: int = 100):
    return (
        db.query(models.Booking)
        .filter(models.Booking.event_id == event_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_booking(db: Session, booking: schemas.BookingCreate):
    # Lock the event row to prevent race conditions under concurrent load
    event = (
        db.query(models.Event)
        .filter(models.Event.id == booking.event_id)
        .with_for_update()
        .first()
    )
    if not event:
        return None, "event_not_found"
    if event.available_tickets <= 0:
        return None, "sold_out"

    user = db.query(models.User).filter(models.User.id == booking.user_id).first()
    if not user:
        return None, "user_not_found"

    event.available_tickets -= 1
    db_booking = models.Booking(user_id=booking.user_id, event_id=booking.event_id)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking, "ok"


def cancel_booking(db: Session, booking_id: int):
    db_booking = (
        db.query(models.Booking)
        .filter(models.Booking.id == booking_id)
        .first()
    )
    if not db_booking:
        return None, "not_found"
    if db_booking.status == "cancelled":
        return None, "already_cancelled"

    event = (
        db.query(models.Event)
        .filter(models.Event.id == db_booking.event_id)
        .with_for_update()
        .first()
    )
    db_booking.status = "cancelled"
    if event:
        event.available_tickets += 1
    db.commit()
    db.refresh(db_booking)
    return db_booking, "ok"


def delete_booking(db: Session, booking_id: int):
    db_booking = (
        db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    )
    if db_booking:
        event = (
            db.query(models.Event)
            .filter(models.Event.id == db_booking.event_id)
            .with_for_update()
            .first()
        )
        if event and db_booking.status == "confirmed":
            event.available_tickets += 1
        db.delete(db_booking)
        db.commit()
        return True
    return False
