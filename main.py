from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import models, database

app = FastAPI(title="Event Booking API")

# Kreiranje tablica (ako već ne postoje)
models.Base.metadata.create_all(bind=database.engine)

@app.get("/")
def home():
    return {"message": "Sustav za rezervacije je spreman!"}



@app.post("/users/")
def create_user(username: str, email: str, db: Session = Depends(database.get_db)):
    db_user = models.User(username=username, email=email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/users/")
def get_all_users(db: Session = Depends(database.get_db)):
    return db.query(models.User).all()


@app.post("/events/")
def create_event(title: str, tickets: int = 100, db: Session = Depends(database.get_db)):
    new_event = models.Event(title=title, available_tickets=tickets)
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return new_event

@app.get("/events/")
def list_events(db: Session = Depends(database.get_db)):
    return db.query(models.Event).all()