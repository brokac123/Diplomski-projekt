import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://user:password@db/booking_db"
)

WORKERS = int(os.environ.get("WORKERS", "1"))
POOL_SIZE = max(5, 60 // WORKERS)       # 1w=60, 2w=30, 4w=15
MAX_OVERFLOW = max(5, 30 // WORKERS)    # 1w=30, 2w=15, 4w=7

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Dependency koji ćemo koristiti u rutama
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
