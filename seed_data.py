import random
from faker import Faker
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import Base, User, Event, Booking


fake = Faker()


def seed_db():
    db: Session = SessionLocal()

    print("--- Započinjem Seeding ---")

    print("Generiram korisnike...")
    users = []
    for _ in range(1000):
        user = User(username=fake.unique.user_name(), email=fake.unique.email())
        db.add(user)
        users.append(user)

    db.commit()  # Commitamo usere da dobijemo ID-ove
    print(f"Ubačeno {len(users)} korisnika.")

    print("Generiram evente...")
    events = []
    locations = ["Zagreb", "Split", "Rijeka", "Osijek", "Zadar", "Varaždin"]

    for _ in range(100):
        total = random.randint(50, 500)
        event = Event(
            title=f"{fake.catch_phrase()} Concert",
            location=random.choice(locations),
            total_tickets=total,
            available_tickets=total,
        )
        db.add(event)
        events.append(event)

    db.commit()
    print(f"Ubačeno {len(events)} evenata.")

    print("Generiram nasumične rezervacije...")
    for _ in range(500):
        user = random.choice(users)
        event = random.choice(events)

        if event.available_tickets > 0:
            booking = Booking(user_id=user.id, event_id=event.id)
            event.available_tickets -= 1
            db.add(booking)

    db.commit()
    print("Seeding završen uspješno!")
    db.close()


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    seed_db()
