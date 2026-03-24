import sys
import random
from datetime import datetime, timedelta
from faker import Faker
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import Base, User, Event, Booking

fake = Faker()
Faker.seed(42)
random.seed(42)

LOCATIONS = ["Zagreb", "Split", "Rijeka", "Osijek", "Zadar", "Varaždin", "Dubrovnik", "Pula"]


def reset_db():
    print("Brišem sve tablice...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Tablice resetirane.")


def seed_db():
    db: Session = SessionLocal()
    print("--- Započinjem Seeding ---")

    # Users
    print("Generiram korisnike...")
    users = []
    now = datetime.utcnow()
    for i in range(1000):
        # Spread created_at: 70% within last 30 days, 30% older (up to 1 year)
        if i < 700:
            created_at = now - timedelta(days=random.randint(0, 30))
        else:
            created_at = now - timedelta(days=random.randint(31, 365))
        user = User(
            username=fake.unique.user_name(),
            email=fake.unique.email(),
            created_at=created_at,
        )
        db.add(user)
        users.append(user)
    db.commit()
    print(f"Ubačeno {len(users)} korisnika.")

    # Events
    print("Generiram evente...")
    events = []
    for i in range(100):
        total = random.randint(50, 500)
        # 60% upcoming, 40% past
        if i < 60:
            event_date = now + timedelta(days=random.randint(1, 180))
        else:
            event_date = now - timedelta(days=random.randint(1, 180))
        event = Event(
            title=f"{fake.catch_phrase()} Concert",
            location=random.choice(LOCATIONS),
            date=event_date,
            price=round(random.uniform(10.0, 200.0), 2),
            total_tickets=total,
            available_tickets=total,
        )
        db.add(event)
        events.append(event)
    db.commit()
    print(f"Ubačeno {len(events)} evenata.")

    # Bookings
    print("Generiram rezervacije...")
    booking_count = 0
    for _ in range(2000):
        user = random.choice(users)
        event = random.choice(events)
        if event.available_tickets > 0:
            # 80% confirmed, 20% cancelled
            status = "confirmed" if random.random() < 0.8 else "cancelled"
            booking = Booking(
                user_id=user.id,
                event_id=event.id,
                status=status,
            )
            # Only reduce available_tickets for confirmed bookings
            if status == "confirmed":
                event.available_tickets -= 1
            db.add(booking)
            booking_count += 1
    db.commit()
    print(f"Ubačeno {booking_count} rezervacija.")

    db.close()
    print("--- Seeding završen uspješno! ---")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_db()
    else:
        Base.metadata.create_all(bind=engine)
    seed_db()
