# API and Database Documentation

This document explains the complete application layer of the project — the FastAPI application, the PostgreSQL database, and every layer in between. It covers the database schema, data models, validation schemas, business logic, all API endpoints, the connection pool design, the deployment configuration, and the seed data strategy. Every design decision that is relevant to the thesis experiment is explicitly called out.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [PostgreSQL Database](#2-postgresql-database)
   - [Schema — Tables and Columns](#21-schema--tables-and-columns)
   - [Relationships and Foreign Keys](#22-relationships-and-foreign-keys)
   - [Indexes](#23-indexes)
   - [The available_tickets Design Decision](#24-the-available_tickets-design-decision)
   - [PostgreSQL Server Configuration](#25-postgresql-server-configuration)
3. [database.py — Connection Pool and Session Management](#3-databasepy--connection-pool-and-session-management)
   - [Connection String](#31-connection-string)
   - [Connection Pool Formula](#32-connection-pool-formula)
   - [Engine Parameters](#33-engine-parameters)
   - [Session Factory and get_db Dependency](#34-session-factory-and-get_db-dependency)
4. [models.py — SQLAlchemy ORM Models](#4-modelspy--sqlalchemy-orm-models)
   - [User Model](#41-user-model)
   - [Event Model](#42-event-model)
   - [Booking Model](#43-booking-model)
   - [Cascade Delete Behavior](#44-cascade-delete-behavior)
5. [schemas.py — Pydantic Validation Schemas](#5-schemaspy--pydantic-validation-schemas)
   - [Schema Inheritance Pattern](#51-schema-inheritance-pattern)
   - [User Schemas](#52-user-schemas)
   - [Event Schemas](#53-event-schemas)
   - [Booking Schemas](#54-booking-schemas)
   - [Response-only Schemas](#55-response-only-schemas)
6. [crud.py — Business Logic and Database Operations](#6-crudpy--business-logic-and-database-operations)
   - [User Operations](#61-user-operations)
   - [Event Operations](#62-event-operations)
   - [Booking Operations](#63-booking-operations)
   - [The create_booking Function — Row-Level Locking](#64-the-create_booking-function--row-level-locking)
   - [The cancel_booking Function](#65-the-cancel_booking-function)
   - [Aggregation Queries](#66-aggregation-queries)
7. [main.py — FastAPI Application and Endpoints](#7-mainpy--fastapi-application-and-endpoints)
   - [Application Startup](#71-application-startup)
   - [Route Ordering — A Critical Detail](#72-route-ordering--a-critical-detail)
   - [Dependency Injection Pattern](#73-dependency-injection-pattern)
   - [Complete Endpoint Reference](#74-complete-endpoint-reference)
8. [Deployment — Dockerfile and Docker Compose](#8-deployment--dockerfile-and-docker-compose)
   - [Dockerfile](#81-dockerfile)
   - [Docker Compose Services](#82-docker-compose-services)
   - [Resource Limits](#83-resource-limits)
   - [WORKERS Environment Variable](#84-workers-environment-variable)
9. [seed_data.py — Database Seeding](#9-seed_datapy--database-seeding)
   - [What Gets Created](#91-what-gets-created)
   - [Distribution Choices](#92-distribution-choices)
   - [The --reset Flag](#93-the---reset-flag)
   - [Why Faker with seed=42](#94-why-faker-with-seed42)

---

## 1. System Overview

The application is a ticket booking API built with FastAPI and backed by PostgreSQL. It exposes a REST API for managing users, events, and bookings. It is intentionally simple in domain logic — the complexity is in the concurrency handling (row-level locking) and in how it is deployed (variable Uvicorn worker count).

The layer stack, from top to bottom:

```
HTTP Client (K6)
      │
      ▼
Uvicorn (ASGI server) — 1, 2, or 4 worker processes
      │
      ▼
FastAPI (main.py) — routing, validation, HTTP responses
      │
      ▼
Pydantic (schemas.py) — request/response validation and serialization
      │
      ▼
SQLAlchemy ORM (crud.py + models.py) — business logic, queries
      │
      ▼
Connection Pool (database.py) — manages DB connections per worker
      │
      ▼
PostgreSQL 15 (Docker container) — persistent storage
```

Each Uvicorn worker is a separate OS process with its own Python interpreter, its own event loop, and its own connection pool. When WORKERS=4, there are 4 independent pools, each managing connections to the same PostgreSQL instance. This is the mechanism by which worker count affects throughput — more workers means more parallel request processing capacity.

---

## 2. PostgreSQL Database

### 2.1 Schema — Tables and Columns

The database contains three tables. SQLAlchemy creates them automatically on startup via `models.Base.metadata.create_all(bind=engine)` in `main.py`.

#### Table: `users`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PRIMARY KEY, auto-increment | Indexed automatically as PK |
| `username` | VARCHAR | UNIQUE, NOT NULL | Indexed explicitly (`index=True`) |
| `email` | VARCHAR | UNIQUE, NOT NULL | Indexed explicitly, validated as email format by Pydantic |
| `created_at` | TIMESTAMP | NOT NULL, default=utcnow | Set at insert time by Python, not the DB |

#### Table: `events`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PRIMARY KEY, auto-increment | — |
| `title` | VARCHAR | NOT NULL | Indexed |
| `location` | VARCHAR | NOT NULL | Indexed — used in search queries |
| `date` | TIMESTAMP | NOT NULL | Indexed — used in upcoming/search queries |
| `price` | FLOAT | NOT NULL, default=0.0 | Used in revenue calculations |
| `total_tickets` | INTEGER | NOT NULL | Set at creation, can be updated |
| `available_tickets` | INTEGER | NOT NULL | Decremented on booking, incremented on cancellation |

#### Table: `bookings`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | INTEGER | PRIMARY KEY, auto-increment | — |
| `user_id` | INTEGER | FOREIGN KEY → users.id, NOT NULL | Indexed |
| `event_id` | INTEGER | FOREIGN KEY → events.id, NOT NULL | Indexed |
| `timestamp` | TIMESTAMP | NOT NULL, default=utcnow | Set at insert time by Python |
| `status` | VARCHAR | NOT NULL, default="confirmed" | Values: "confirmed" or "cancelled". Indexed |

---

### 2.2 Relationships and Foreign Keys

```
users (1) ──────────── (many) bookings
events (1) ─────────── (many) bookings
```

- A user can have many bookings.
- An event can have many bookings.
- A booking belongs to exactly one user and one event.
- Both foreign keys (`user_id`, `event_id`) have `ON DELETE CASCADE` behavior enforced at the ORM level via SQLAlchemy's `cascade="all, delete-orphan"` on both parent models.

---

### 2.3 Indexes

SQLAlchemy creates the following indexes automatically based on `index=True` declarations in `models.py`:

| Table | Column | Index type | Purpose |
|-------|--------|------------|---------|
| users | id | Primary key (B-tree) | PK lookup |
| users | username | B-tree, unique | Uniqueness enforcement |
| users | email | B-tree, unique | Uniqueness enforcement |
| events | id | Primary key (B-tree) | PK lookup |
| events | title | B-tree | Search by title (not currently used in queries) |
| events | location | B-tree | `search_events` filter: `WHERE location = ?` |
| events | date | B-tree | `get_upcoming_events`: `WHERE date > now() ORDER BY date` |
| bookings | id | Primary key (B-tree) | PK lookup |
| bookings | user_id | B-tree | `get_bookings_by_user`: `WHERE user_id = ?` |
| bookings | event_id | B-tree | `get_bookings_by_event`: `WHERE event_id = ?` |
| bookings | status | B-tree | `get_event_stats`, `get_global_stats`: `WHERE status = 'confirmed'` |

All indexes are B-tree (PostgreSQL default). Because the dataset is small (1000 users, 100 events, ~1500 bookings after seeding), these indexes ensure near-constant-time lookups regardless of load. This is an intentional design choice — the database is kept fast so that the worker CPU event loop is the bottleneck, not database I/O.

---

### 2.4 The available_tickets Design Decision

`available_tickets` is stored as a column on the `events` table rather than being computed on every read by counting confirmed bookings. This is a **denormalized** design — the data could be derived from `COUNT(bookings WHERE event_id=X AND status='confirmed')`, but it is instead maintained as a running counter.

**Why this matters:**
- **Reads are O(1)** — fetching an event always returns `available_tickets` directly. No join or aggregate is needed.
- **Writes require locking** — because two concurrent booking requests could both read `available_tickets = 1`, both decrement it, and produce a negative value (overselling), every booking write must acquire a row-level lock on the event before reading and decrementing. This is implemented via `SELECT ... FOR UPDATE` in `create_booking`.
- **This is the source of the contention test invariant** — with 283 initial tickets and 50 concurrent VUs all targeting the same event, exactly 283 bookings succeed because the lock serializes every write. The 284th request always sees `available_tickets = 0` and gets a 409 response.

An alternative design — computing availability from bookings count — would eliminate the need for `FOR UPDATE` on reads but would make every event read more expensive. The chosen approach optimizes for read performance at the cost of requiring careful write locking.

---

### 2.5 PostgreSQL Server Configuration

PostgreSQL is started with custom parameters set in `docker-compose.yml`:

```
postgres
  -c shared_buffers=512MB
  -c work_mem=8MB
  -c max_connections=100
  -c effective_cache_size=1GB
```

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `shared_buffers` | 512MB | Amount of memory PostgreSQL uses for its shared buffer cache (data pages). Higher value = more data cached in memory = fewer disk reads. Default is typically 128MB. |
| `work_mem` | 8MB | Memory per sort/hash operation per query. Affects ORDER BY, GROUP BY, and JOIN performance. Multiple operations per query can each use this amount. |
| `max_connections` | 100 | Maximum number of simultaneous client connections PostgreSQL will accept. This must be higher than the total connection pool size across all workers. With 1w (pool_size=60, max_overflow=30), the theoretical max is 90 connections, comfortably under 100. |
| `effective_cache_size` | 1GB | A hint to the query planner about how much memory is available for caching (including OS file cache). Does not allocate memory — it only influences query plan decisions. |

**Why max_connections=100 is safe:** The connection pool formula ensures that total connections never exceed this limit. With 4 workers (pool_size=15, max_overflow=7 each), the maximum is 4 × (15+7) = 88 connections. With 1 worker (pool_size=60, max_overflow=30), the maximum is 90. Both are within the 100-connection limit.

---

## 3. database.py — Connection Pool and Session Management

`database.py` is the most thesis-relevant file in the codebase. It configures how each Uvicorn worker connects to PostgreSQL.

### 3.1 Connection String

```python
SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://user:password@db/booking_db"
)
```

The connection string is read from the `DATABASE_URL` environment variable (set in `docker-compose.yml`). The default value connects to the `db` Docker service (hostname `db`, resolved by Docker's internal DNS) using `psycopg2` (the default PostgreSQL driver for SQLAlchemy).

---

### 3.2 Connection Pool Formula

```python
WORKERS = int(os.environ.get("WORKERS", "1"))
POOL_SIZE = max(5, 60 // WORKERS)       # 1w=60, 2w=30, 4w=15
MAX_OVERFLOW = max(5, 30 // WORKERS)    # 1w=30, 2w=15, 4w=7
```

This is the **central experimental design decision** of the thesis. The connection pool is scaled inversely with worker count so that the total number of database connections remains approximately constant regardless of how many workers are running.

| Config | WORKERS | POOL_SIZE | MAX_OVERFLOW | Max connections per worker | Total max connections |
|--------|---------|-----------|--------------|--------------------------|----------------------|
| 1w | 1 | 60 | 30 | 90 | 90 |
| 2w | 2 | 30 | 15 | 45 | 90 |
| 4w | 4 | 15 | 7 | 22 | 88 |

**Why this formula:**
- `POOL_SIZE` is the number of connections kept open permanently (idle or active).
- `MAX_OVERFLOW` is the number of additional connections allowed above `POOL_SIZE` during traffic spikes. These connections are created on demand and closed when returned to the pool.
- `60 // WORKERS` divides the total connection budget equally across workers.
- `max(5, ...)` ensures a minimum of 5 connections per pool regardless of worker count, preventing pathological under-provisioning for very high worker counts.

**Why this matters for the thesis:** If the pool were not scaled, adding workers could create a connection bottleneck: 4 workers with 60 connections each = 240 connections, exceeding PostgreSQL's `max_connections=100`. The formula ensures the database is not the bottleneck — it removes the DB connection layer as a confounding variable, isolating worker CPU as the independent variable being studied.

---

### 3.3 Engine Parameters

```python
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
)
```

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `pool_size` | Computed | Permanent connections in the pool |
| `max_overflow` | Computed | Temporary connections above pool_size |
| `pool_pre_ping` | True | Before giving a connection to a request handler, SQLAlchemy sends a lightweight `SELECT 1` to check the connection is still alive. Prevents "connection closed" errors after idle periods or DB restarts. |
| `pool_recycle` | 1800 | Connections older than 1800 seconds (30 minutes) are closed and replaced. Prevents issues with PostgreSQL's `tcp_keepalives_idle` timeout and stale connection state. |

---

### 3.4 Session Factory and get_db Dependency

```python
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

`SessionLocal` is a factory that creates database sessions. Key settings:
- `autocommit=False` — every transaction must be explicitly committed with `db.commit()`. This gives full control over when changes are written to disk.
- `autoflush=False` — SQLAlchemy does not automatically flush pending changes to the DB before queries. Changes are only sent when explicitly committed. This prevents unintended intermediate writes.

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

`get_db` is a FastAPI **dependency** — it is injected into every route handler via `db: Session = Depends(get_db)`. Its lifecycle:

1. A new `SessionLocal` session is created (acquires a connection from the pool).
2. The session is yielded to the route handler.
3. The route handler runs (executes queries, commits or raises exceptions).
4. If an exception occurs: `db.rollback()` undoes any uncommitted changes, then the exception re-raises.
5. In all cases: `db.close()` returns the connection to the pool.

**One session per request:** Each HTTP request gets exactly one session, one connection from the pool, and one transaction scope. The connection is held for the duration of the request and returned immediately when the response is sent. This is standard SQLAlchemy per-request session management.

---

## 4. models.py — SQLAlchemy ORM Models

SQLAlchemy ORM models define the Python representation of database tables. They inherit from `Base = declarative_base()` defined in `database.py`.

### 4.1 User Model

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="user", cascade="all, delete-orphan")
```

- `default=datetime.utcnow` — the function reference (not a call) is passed. SQLAlchemy calls it at insert time. This means each user gets the timestamp of when the Python code ran the insert, not the database server time.
- `relationship("Booking", ...)` — declares the ORM relationship. SQLAlchemy can load a user's bookings via `user.bookings` without a manual JOIN query (lazy loading by default).
- `cascade="all, delete-orphan"` — when a user is deleted, all their bookings are automatically deleted too. SQLAlchemy handles this at the ORM level (it does not rely on `ON DELETE CASCADE` in the database schema).

---

### 4.2 Event Model

```python
class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    location = Column(String, index=True)
    date = Column(DateTime, index=True)
    price = Column(Float, default=0.0)
    total_tickets = Column(Integer)
    available_tickets = Column(Integer)

    bookings = relationship("Booking", back_populates="event", cascade="all, delete-orphan")
```

- `total_tickets` — the capacity of the event. Set at creation, can be updated via `PUT /events/{id}` (with a guard preventing reduction below already-booked count).
- `available_tickets` — the current remaining capacity. Set equal to `total_tickets` at creation (`create_event` explicitly sets `available_tickets=event.total_tickets`). Modified only in `create_booking` (−1) and `cancel_booking` / `delete_booking` (+1).

---

### 4.3 Booking Model

```python
class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    event_id = Column(Integer, ForeignKey("events.id"), index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="confirmed", index=True)

    user = relationship("User", back_populates="bookings")
    event = relationship("Event", back_populates="bookings")
```

- `status` — only two values ever appear: `"confirmed"` and `"cancelled"`. There is no enum constraint at the DB level — the constraint is enforced by the application logic (only `create_booking` sets `"confirmed"` and only `cancel_booking` sets `"cancelled"`).
- A cancelled booking is never deleted — it remains in the table with `status="cancelled"`. This is intentional: it preserves the audit trail and keeps ticket inventory consistent (cancellation increments `available_tickets`, not deletion).

---

### 4.4 Cascade Delete Behavior

Both `User` and `Event` have `cascade="all, delete-orphan"` on their `bookings` relationship. This means:

- `DELETE /users/{id}` → all bookings by that user are deleted by SQLAlchemy (not PostgreSQL FK cascade)
- `DELETE /events/{id}` → all bookings for that event are deleted

**Important:** The `delete_booking` CRUD function explicitly checks `if db_booking.status == "confirmed"` before incrementing `available_tickets`. Cascade-deleted bookings (via user or event deletion) do not go through this logic — they are deleted directly. This is acceptable because deleting an event removes it entirely; the ticket count no longer matters.

---

## 5. schemas.py — Pydantic Validation Schemas

Pydantic schemas serve two roles: **request validation** (incoming data) and **response serialization** (outgoing data). FastAPI uses them automatically — request bodies are validated against the input schema before the route handler runs, and return values are serialized through the response schema before being sent to the client.

### 5.1 Schema Inheritance Pattern

Each resource follows a three-class inheritance pattern:

```
XxxBase (shared fields)
├── XxxCreate (input — inherits Base, used for POST requests)
├── XxxUpdate (partial input — all Optional, used for PATCH)
└── Xxx (output — inherits Base, adds DB-generated fields like id, timestamp)
```

The `Xxx` (output) class includes `model_config = ConfigDict(from_attributes=True)`. This tells Pydantic to read field values from object attributes (SQLAlchemy model instances) rather than from dictionary keys. Without this, FastAPI could not serialize SQLAlchemy ORM objects into JSON responses.

---

### 5.2 User Schemas

```python
class UserBase(BaseModel):
    username: str
    email: EmailStr          # Pydantic validates email format

class UserCreate(UserBase):
    pass                     # POST /users/ — same fields as Base

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None  # PATCH /users/{id} — all fields optional

class User(UserBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)  # allows ORM → Pydantic
```

`EmailStr` is a Pydantic-provided type that validates the format of email addresses. If a client sends `email: "notanemail"`, Pydantic rejects it with a 422 Unprocessable Entity response before the route handler is even called.

`UserUpdate` uses `Optional[...] = None` for all fields so that a PATCH request can include only the fields it wants to change. The `crud.patch_user` function uses `user.model_dump(exclude_unset=True)` to get only the fields that were actually provided in the request, then sets them on the model.

---

### 5.3 Event Schemas

```python
class EventBase(BaseModel):
    title: str
    location: str
    date: datetime
    price: float
    total_tickets: int

class EventCreate(EventBase):
    pass

class EventUpdate(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    date: Optional[datetime] = None
    price: Optional[float] = None
    total_tickets: Optional[int] = None

class Event(EventBase):
    id: int
    available_tickets: int       # not in EventCreate — computed by the API
    model_config = ConfigDict(from_attributes=True)
```

`available_tickets` is intentionally absent from `EventCreate`. The client only provides `total_tickets`. The API sets `available_tickets = total_tickets` automatically in `create_event`. This prevents clients from creating events with inconsistent ticket counts.

---

### 5.4 Booking Schemas

```python
class BookingBase(BaseModel):
    event_id: int
    user_id: int

class BookingCreate(BookingBase):
    pass                          # POST /bookings/ — just event_id and user_id

class Booking(BookingBase):
    id: int
    timestamp: datetime
    status: str                   # "confirmed" or "cancelled"
    model_config = ConfigDict(from_attributes=True)
```

The booking creation request is deliberately minimal — just `event_id` and `user_id`. The API handles all the business logic: checking availability, locking the event row, decrementing tickets, setting the initial status to `"confirmed"`.

There is no `BookingUpdate` schema because bookings are never partially updated. The only state change is cancellation, handled by a dedicated `PATCH /bookings/{id}/cancel` endpoint that takes no request body.

---

### 5.5 Response-only Schemas

Three schemas exist only for API responses — they are never used as input schemas.

**EventStats** — returned by `GET /events/{id}/stats`:
```python
class EventStats(BaseModel):
    event_id: int
    title: str
    total_tickets: int
    available_tickets: int
    booked_tickets: int        # total_tickets - available_tickets
    occupancy_pct: float       # (booked / total) * 100, rounded to 2 decimal places
    total_revenue: float       # confirmed_bookings * event.price
    cancelled_bookings: int
```

**PopularEvent** — one item in the list returned by `GET /events/popular`:
```python
class PopularEvent(BaseModel):
    event_id: int
    title: str
    location: str
    date: datetime
    price: float
    confirmed_bookings: int    # the count used for ranking
```

**GlobalStats** — returned by `GET /stats`:
```python
class GlobalStats(BaseModel):
    total_users: int
    total_events: int
    total_bookings: int
    confirmed_bookings: int
    cancelled_bookings: int
    total_revenue: float          # SUM(event.price) for all confirmed bookings
    avg_occupancy_pct: float      # average across all events
    new_users_last_30_days: int
```

These three schemas have no `from_attributes=True` because `crud.py` constructs them manually (not from ORM objects directly).

---

## 6. crud.py — Business Logic and Database Operations

`crud.py` contains all database operations. It is the only file that issues SQL queries (via SQLAlchemy ORM). `main.py` never queries the database directly — it calls `crud` functions and translates their return values into HTTP responses.

### 6.1 User Operations

| Function | SQL equivalent | Notes |
|----------|----------------|-------|
| `get_user(db, user_id)` | `SELECT * FROM users WHERE id = ? LIMIT 1` | Returns None if not found |
| `get_users(db, skip, limit)` | `SELECT * FROM users OFFSET ? LIMIT ?` | No ordering — returns rows in insertion order |
| `create_user(db, user)` | `INSERT INTO users ...` | `db.refresh(db_user)` re-reads from DB to populate auto-generated `id` and `created_at` |
| `delete_user(db, user_id)` | `DELETE FROM users WHERE id = ?` | Cascade handled by SQLAlchemy |
| `update_user(db, user_id, user)` | `UPDATE users SET username=?, email=? WHERE id=?` | Full replacement — both fields always updated |
| `patch_user(db, user_id, user)` | `UPDATE users SET {provided fields} WHERE id=?` | Partial update via `model_dump(exclude_unset=True)` |

**PATCH vs PUT:** `update_user` (PUT) always updates all fields. `patch_user` (PATCH) only updates the fields included in the request. `model_dump(exclude_unset=True)` returns a dictionary containing only the fields that were explicitly set in the request body — fields left at their `None` default are excluded. The loop `for key, value in ... setattr(db_user, key, value)` then applies only those changes.

---

### 6.2 Event Operations

| Function | SQL equivalent | Notes |
|----------|----------------|-------|
| `get_event(db, event_id)` | `SELECT * FROM events WHERE id = ? LIMIT 1` | — |
| `get_events(db, skip, limit)` | `SELECT * FROM events OFFSET ? LIMIT ?` | — |
| `create_event(db, event)` | `INSERT INTO events ...` | Sets `available_tickets = total_tickets` |
| `delete_event(db, event_id)` | `DELETE FROM events WHERE id = ?` | Cascade handles bookings |
| `update_event(db, event_id, event)` | `UPDATE events SET ... WHERE id = ?` | Guards against setting `total_tickets` below already-booked count |
| `patch_event(db, event_id, event)` | Partial update | Same pattern as `patch_user` |
| `get_upcoming_events(db, skip, limit)` | `SELECT * FROM events WHERE date > now() ORDER BY date ASC LIMIT ?` | Uses the date index |
| `search_events(db, location, date_from, date_to, skip, limit)` | Dynamic WHERE clause | Filters are additive — only applied if the parameter is not None |

**update_event guard:**
```python
booked_tickets = db_event.total_tickets - db_event.available_tickets
if event.total_tickets < booked_tickets:
    return None, "invalid"
```
If someone tries to reduce `total_tickets` to 50 but 80 tickets are already booked, the update is rejected with a 400 error. `available_tickets` is recalculated as `new_total - already_booked` to maintain consistency.

**search_events dynamic query:**
```python
query = db.query(models.Event)
if location:
    query = query.filter(models.Event.location == location)
if date_from:
    query = query.filter(models.Event.date >= date_from)
if date_to:
    query = query.filter(models.Event.date <= date_to)
return query.order_by(models.Event.date.asc()).offset(skip).limit(limit).all()
```
The query object is built incrementally. Filters are only added if the corresponding parameter was provided by the client. This produces a single SQL query with only the relevant WHERE clauses.

---

### 6.3 Booking Operations

| Function | SQL equivalent | Notes |
|----------|----------------|-------|
| `get_booking(db, booking_id)` | `SELECT * FROM bookings WHERE id = ? LIMIT 1` | — |
| `get_bookings(db, skip, limit)` | `SELECT * FROM bookings OFFSET ? LIMIT ?` | — |
| `get_bookings_by_user(db, user_id, skip, limit)` | `SELECT * FROM bookings WHERE user_id = ? LIMIT ?` | — |
| `get_bookings_by_event(db, event_id, skip, limit)` | `SELECT * FROM bookings WHERE event_id = ? LIMIT ?` | — |
| `create_booking(db, booking)` | See below — uses `FOR UPDATE` | Core thesis operation |
| `cancel_booking(db, booking_id)` | See below — uses `FOR UPDATE` | — |
| `delete_booking(db, booking_id)` | `DELETE FROM bookings WHERE id = ?` | Returns ticket if booking was confirmed |

---

### 6.4 The create_booking Function — Row-Level Locking

This is the most important function in the codebase for the thesis. It is the critical section that prevents ticket overselling under concurrent load.

```python
def create_booking(db: Session, booking: schemas.BookingCreate):
    # Step 1: Lock the event row
    event = (
        db.query(models.Event)
        .filter(models.Event.id == booking.event_id)
        .with_for_update()
        .first()
    )

    # Step 2: Check existence and availability
    if not event:
        return None, "event_not_found"
    if event.available_tickets <= 0:
        return None, "sold_out"

    # Step 3: Check user existence
    user = db.query(models.User).filter(models.User.id == booking.user_id).first()
    if not user:
        return None, "user_not_found"

    # Step 4: Decrement and commit
    event.available_tickets -= 1
    db_booking = models.Booking(user_id=booking.user_id, event_id=booking.event_id)
    db.add(db_booking)
    db.commit()
    db.refresh(db_booking)
    return db_booking, "ok"
```

**What `.with_for_update()` does:**

The SQLAlchemy `.with_for_update()` call generates `SELECT ... FOR UPDATE` in SQL. This is PostgreSQL's row-level locking mechanism. When a transaction executes `SELECT ... FOR UPDATE` on a row, it acquires an exclusive lock on that row. Any other transaction that also tries `SELECT ... FOR UPDATE` on the same row will **block** (wait) until the first transaction commits or rolls back.

**Why this is necessary — the race condition without locking:**

Without locking, two concurrent requests could produce this sequence:

```
Transaction A: reads available_tickets = 1
Transaction B: reads available_tickets = 1
Transaction A: available_tickets -= 1 → writes 0, commits
Transaction B: available_tickets -= 1 → writes 0, commits (BUG: both think they got the last ticket)
```

Result: two bookings created, `available_tickets = 0`, but it was decremented twice from 1. The count is consistent, but two people got the last ticket.

**With FOR UPDATE:**

```
Transaction A: SELECT FOR UPDATE → acquires lock, reads available_tickets = 1
Transaction B: SELECT FOR UPDATE → blocks, waiting for A's lock
Transaction A: available_tickets -= 1 → writes 0, commits, releases lock
Transaction B: lock acquired, reads available_tickets = 0 → returns "sold_out"
```

Result: exactly one booking created, ticket count consistent.

**Transaction scope:** The lock is held from the `SELECT FOR UPDATE` until `db.commit()`. During this window, all other transactions trying to book the same event are queued by PostgreSQL. This is what the contention test measures — the latency added by lock waiting when 50 VUs all target the same event.

**The 283-booking invariant:** Because every booking creation is serialized through this lock, the total successful bookings for an event can never exceed its initial `available_tickets`. In the contention test, event 1 starts with 283 tickets (seeded value), and exactly 283 bookings succeed across all 5 runs and all worker configs. The lock makes worker count irrelevant to correctness.

---

### 6.5 The cancel_booking Function

```python
def cancel_booking(db: Session, booking_id: int):
    db_booking = (
        db.query(models.Booking)
        .filter(models.Booking.id == booking_id)
        .with_for_update()
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
```

Cancellation also uses `FOR UPDATE` — on both the booking row and the event row. This prevents two concurrent cancellations of the same booking from both incrementing `available_tickets`. The first `FOR UPDATE` on the booking row ensures only one transaction can change the booking status at a time. The guard `if db_booking.status == "cancelled"` returns an error if the booking was already cancelled (which can only happen if another transaction cancelled it between this transaction's lock acquisition and status check — which `FOR UPDATE` prevents entirely, so this guard is mainly for sequential duplicate requests).

The event is also locked (`FOR UPDATE`) before incrementing `available_tickets` because another concurrent booking could be in the process of reading and decrementing it simultaneously. Locking both rows prevents the increment from racing with a decrement.

---

### 6.6 Aggregation Queries

Three functions execute non-trivial SQL aggregations:

**get_event_stats:**
```python
# Two separate COUNT queries + event fields
confirmed = db.query(func.count(models.Booking.id))
    .filter(models.Booking.event_id == event_id, models.Booking.status == "confirmed")
    .scalar()
cancelled = db.query(func.count(models.Booking.id))
    .filter(models.Booking.event_id == event_id, models.Booking.status == "cancelled")
    .scalar()
```
SQL: `SELECT COUNT(id) FROM bookings WHERE event_id=? AND status='confirmed'`
Three queries total (one for the event, two counts). Could be merged into one query with conditional aggregation but is kept simple. Results are assembled into an `EventStats` Pydantic model manually.

**get_popular_events:**
```python
db.query(models.Event, func.count(models.Booking.id).label("confirmed_bookings"))
    .join(models.Booking, models.Booking.event_id == models.Event.id)
    .filter(models.Booking.status == "confirmed")
    .group_by(models.Event.id)
    .order_by(func.count(models.Booking.id).desc())
    .limit(limit)
    .all()
```
SQL: `SELECT events.*, COUNT(bookings.id) FROM events JOIN bookings ON ... WHERE bookings.status='confirmed' GROUP BY events.id ORDER BY COUNT DESC LIMIT ?`
This is the most expensive read query — a JOIN with GROUP BY and ORDER BY. With the small dataset it executes quickly, but under load this is the query that makes `heavy_aggregations` the slowest scenario in the endpoint benchmark.

**get_global_stats:**
```python
# avg_occupancy — computed in SQL
func.avg(
    (models.Event.total_tickets - models.Event.available_tickets) * 100.0 / models.Event.total_tickets
)

# total_revenue — JOIN + SUM
db.query(func.sum(models.Event.price))
    .join(models.Booking, models.Booking.event_id == models.Event.id)
    .filter(models.Booking.status == "confirmed")
    .scalar()
```
This function executes 6 separate queries (total_users, total_events, total_bookings, confirmed, cancelled, new_users, avg_occupancy, total_revenue — some combined). It is the most expensive endpoint in the API because it scans multiple entire tables. The `GET /stats` endpoint represents 2% of traffic in `trafficMix()` for this reason.

---

## 7. main.py — FastAPI Application and Endpoints

### 7.1 Application Startup

```python
models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="Booking API - Verzija 1")
Instrumentator().instrument(app).expose(app)
```

Three things happen at startup:
1. **`create_all`** — SQLAlchemy inspects the database and creates any tables that don't already exist. If tables exist with the correct schema, this is a no-op. It does not drop and recreate tables.
2. **`FastAPI()`** — creates the application instance. The `title` appears in the auto-generated OpenAPI documentation at `/docs`.
3. **`Instrumentator().instrument(app).expose(app)`** — the `prometheus_fastapi_instrumentator` library wraps every route handler with a timing decorator and exposes a `/metrics` endpoint. Prometheus scrapes this endpoint to collect per-endpoint HTTP metrics (request count, latency histograms, error rates).

---

### 7.2 Route Ordering — A Critical Detail

The events router registers routes in this order:

```python
@app.get("/events/")          # list all
@app.get("/events/upcoming")  # upcoming events
@app.get("/events/search")    # search
@app.get("/events/popular")   # popular
@app.get("/events/{event_id}") # single event — must come LAST
```

`/events/upcoming`, `/events/search`, and `/events/popular` **must** be registered before `/events/{event_id}`. FastAPI matches routes in registration order. If `{event_id}` were registered first, a request to `/events/upcoming` would match it with `event_id="upcoming"`, fail the integer cast, and return a 422 error instead of calling the correct handler.

This is a FastAPI routing rule: **static path segments must come before path parameters** when they share the same prefix.

---

### 7.3 Dependency Injection Pattern

Every route that needs database access includes `db: Session = Depends(get_db)` in its signature:

```python
@app.get("/users/{user_id}", response_model=schemas.User)
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user
```

FastAPI calls `get_db()` before calling the route handler, passes the session as `db`, and calls the `finally` block of `get_db()` after the response is sent. The route handler itself never opens or closes connections — it just receives a ready-to-use session and passes it to `crud` functions.

**Error handling pattern:** Most route handlers follow a two-step pattern:
1. Call the `crud` function, which returns `(result, reason)` tuples for operations that can fail
2. Check the reason and raise `HTTPException` with the appropriate status code

This separates the HTTP layer (status codes, error messages) from the business logic layer (what actually went wrong and why).

---

### 7.4 Complete Endpoint Reference

#### Health

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| GET | `/health` | `{"status": "ok"}` | Liveness check. Used by K6 `checkApiHealth()` and Docker healthcheck. |

---

#### Users

| Method | Path | Request Body | Response | Status Codes | Notes |
|--------|------|-------------|----------|--------------|-------|
| GET | `/users/` | — | `List[User]` | 200 | `skip`, `limit` query params (default: 0, 100) |
| GET | `/users/{user_id}` | — | `User` | 200, 404 | 404 if user not found |
| POST | `/users/` | `UserCreate` | `User` | 200 | Creates user; 422 if email invalid |
| PUT | `/users/{user_id}` | `UserCreate` | `User` | 200, 404 | Full replacement — both fields required |
| PATCH | `/users/{user_id}` | `UserUpdate` | `User` | 200, 404 | Partial update — any field optional |
| DELETE | `/users/{user_id}` | — | `{"message": "..."}` | 200, 404 | Cascades to bookings |
| GET | `/users/{user_id}/bookings` | — | `List[Booking]` | 200 | User's booking history. `skip`, `limit` supported |

---

#### Events

| Method | Path | Request Body | Response | Status Codes | Notes |
|--------|------|-------------|----------|--------------|-------|
| GET | `/events/` | — | `List[Event]` | 200 | `skip`, `limit` |
| GET | `/events/upcoming` | — | `List[Event]` | 200 | Events where `date > now()`, sorted by date ASC |
| GET | `/events/search` | — | `List[Event]` | 200 | Query params: `location`, `date_from`, `date_to`. All optional |
| GET | `/events/popular` | — | `List[PopularEvent]` | 200 | Sorted by confirmed booking count DESC. `limit` param (default 10) |
| GET | `/events/{event_id}` | — | `Event` | 200, 404 | — |
| GET | `/events/{event_id}/stats` | — | `EventStats` | 200, 404 | Aggregated stats: occupancy, revenue, cancelled count |
| GET | `/events/{event_id}/bookings` | — | `List[Booking]` | 200 | All bookings for the event. `skip`, `limit` |
| POST | `/events/` | `EventCreate` | `Event` | 200 | `available_tickets` auto-set to `total_tickets` |
| PUT | `/events/{event_id}` | `EventCreate` | `Event` | 200, 400, 404 | 400 if `total_tickets` < already booked |
| PATCH | `/events/{event_id}` | `EventUpdate` | `Event` | 200, 404 | Partial update |
| DELETE | `/events/{event_id}` | — | `{"message": "..."}` | 200, 404 | Cascades to bookings |

---

#### Bookings

| Method | Path | Request Body | Response | Status Codes | Notes |
|--------|------|-------------|----------|--------------|-------|
| GET | `/bookings/` | — | `List[Booking]` | 200 | `skip`, `limit` |
| GET | `/bookings/{booking_id}` | — | `Booking` | 200, 404 | — |
| POST | `/bookings/` | `BookingCreate` | `Booking` | 200, 404, 409 | 409 = sold out. Uses `SELECT FOR UPDATE` on event row |
| PATCH | `/bookings/{booking_id}/cancel` | — | `Booking` | 200, 404, 409 | 409 = already cancelled. Uses `SELECT FOR UPDATE` |
| DELETE | `/bookings/{booking_id}` | — | `{"message": "..."}` | 200, 404 | Returns ticket to `available_tickets` if was confirmed |

---

#### Stats

| Method | Path | Response | Status Codes | Notes |
|--------|------|----------|--------------|-------|
| GET | `/stats` | `GlobalStats` | 200 | Aggregates across all tables. Most expensive endpoint. |

---

#### Automatically Added by Instrumentator

| Method | Path | Description |
|--------|------|-------------|
| GET | `/metrics` | Prometheus metrics endpoint — request counts, latency histograms per endpoint |

---

## 8. Deployment — Dockerfile and Docker Compose

### 8.1 Dockerfile

```dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY ./app ./app
COPY seed_data.py .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- `python:3.11-slim` — minimal Python 3.11 image without unnecessary system packages.
- `PYTHONUNBUFFERED=1` — disables Python's output buffering so that `print()` statements appear in Docker logs immediately rather than being held in a buffer.
- `WORKDIR /code` — all subsequent commands run from `/code`. Copies go into `/code/app/` and `/code/seed_data.py`.
- The `CMD` is the **default** command — it is overridden by `docker-compose.yml` which passes the actual worker count via the `command` field.

---

### 8.2 Docker Compose Services

The compose file defines 5 services:

**db (PostgreSQL 15)**
- Custom startup command with tuned parameters (see Section 2.5)
- Named volume `postgres_data` — data persists across container restarts
- Healthcheck: `pg_isready -U user -d booking_db` — ensures the API container does not start until PostgreSQL is ready to accept connections
- The `api` service has `depends_on: db: condition: service_healthy`

**api (FastAPI + Uvicorn)**
- Built from `Dockerfile`
- Port 8000 exposed to host
- `command` override: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-1}`
  - `${WORKERS:-1}` reads the `WORKERS` environment variable from the `.env` file; defaults to 1 if not set
- `restart: unless-stopped` — automatically restarts on crash
- Healthcheck: pings `/health` with Python's `urllib` (no curl needed in slim image)

**prometheus**
- `--web.enable-remote-write-receiver` — enables the endpoint that K6 pushes metrics to (`/api/v1/write`)
- `--storage.tsdb.retention.time=90d` — keeps metric data for 90 days
- `depends_on: api: condition: service_healthy` — Prometheus waits for the API to be healthy before starting (ensures `/metrics` is available when scraping begins)

**grafana**
- Mounts provisioning files — datasources and dashboards are auto-configured on startup
- No manual Grafana setup needed after `docker compose up`

**node-exporter**
- Collects host system CPU, memory, and disk metrics
- Exposes port 9100 for Prometheus to scrape

---

### 8.3 Resource Limits

Resource limits are set via Docker's `deploy.resources.limits`:

| Service | CPU limit | Memory limit |
|---------|-----------|-------------|
| api | 4.0 CPUs | 2 GB |
| db | 3.0 CPUs | 2 GB |
| prometheus | 1.0 CPU | 512 MB |
| grafana | 0.5 CPU | 256 MB |
| node-exporter | 0.25 CPU | 128 MB |

The API and DB receive the most resources because they are the system under test. The API limit of 4 CPUs allows all 4 workers to run in parallel without competing with each other for CPU time beyond what the host OS scheduler already manages. These limits apply to the Docker containers inside the WSL2 VM — the VM itself receives CPU dynamically from Windows.

---

### 8.4 WORKERS Environment Variable

The `WORKERS` environment variable is the single control variable of the entire thesis experiment. It flows through the stack as follows:

1. **`.env` file** — `WORKERS=4` (or 1, or 2)
2. **`docker-compose.yml`** — passes `WORKERS` to the api container via the `environment` block and uses `${WORKERS:-1}` in the `command`
3. **Uvicorn** — `--workers 4` spawns 4 worker processes
4. **`database.py`** — `WORKERS = int(os.environ.get("WORKERS", "1"))` reads the value and computes `POOL_SIZE` and `MAX_OVERFLOW`

Each worker process reads `WORKERS` independently at startup and creates its own connection pool with the computed size. This is why the pool formula produces different pool sizes for different worker counts — each process needs a proportionally smaller pool so the total stays within PostgreSQL's connection limit.

---

## 9. seed_data.py — Database Seeding

`seed_data.py` populates the database with realistic test data. It is run once before testing begins (or with `--reset` to wipe and re-seed).

### 9.1 What Gets Created

| Entity | Count | Notes |
|--------|-------|-------|
| Users | 1,000 | Unique usernames and emails generated by Faker |
| Events | 100 | Randomized titles, locations, dates, prices, ticket counts |
| Bookings | ~1,500 | Attempted 2,000 times; skips if event has no tickets |

---

### 9.2 Distribution Choices

**Users — created_at distribution:**
```python
if i < 700:
    created_at = now - timedelta(days=random.randint(0, 30))   # 70% recent
else:
    created_at = now - timedelta(days=random.randint(31, 365)) # 30% older
```
70% of users were "created" within the last 30 days. This makes the `new_users_last_30_days` field in `GlobalStats` return a realistic non-trivial value (~700) rather than 0 or 1000.

**Events — date distribution:**
```python
if i < 60:
    event_date = now + timedelta(days=random.randint(1, 180))  # 60% upcoming
else:
    event_date = now - timedelta(days=random.randint(1, 180))  # 40% past
```
60 out of 100 events are in the future. The `get_upcoming_events` query (`WHERE date > now()`) returns ~60 results. This keeps the upcoming events endpoint returning a realistic non-empty list.

**Events — ticket counts:**
```python
total = random.randint(50, 500)
```
Each event has between 50 and 500 tickets. The contention test targets event 1 specifically — event 1 always has 283 tickets (the seeded random value for seed=42, which is deterministic). This is why the contention invariant is always exactly 283.

**Bookings — status distribution:**
```python
status = "confirmed" if random.random() < 0.8 else "cancelled"
if status == "confirmed":
    event.available_tickets -= 1
```
80% of seeded bookings are confirmed, 20% are cancelled. Cancelled bookings do not decrement `available_tickets`. This means after seeding, events have used some of their capacity (from confirmed bookings) but still have plenty of tickets available for the test suite to create bookings.

---

### 9.3 The --reset Flag

```python
if "--reset" in sys.argv:
    reset_db()
else:
    Base.metadata.create_all(bind=engine)
seed_db()
```

Without `--reset`: creates tables if they don't exist, then seeds. If the database already has data, seeding adds more rows on top.

With `--reset`:
```python
def reset_db():
    Base.metadata.drop_all(bind=engine)   # drop all tables
    Base.metadata.create_all(bind=engine) # recreate empty tables
```
Drops all tables and recreates them empty before seeding. This is required before the contention test because thousands of booking attempts during Phase B tests drain `available_tickets` to 0 on most events. Without resetting, the contention test would immediately get 409 responses on every attempt and produce 0 successful bookings instead of 283.

Command: `docker compose exec api python seed_data.py --reset`

---

### 9.4 Why Faker with seed=42

```python
fake = Faker()
Faker.seed(42)
random.seed(42)
```

Setting a fixed seed makes seeding **deterministic**. Every time `seed_data.py` runs (without `--reset` changing the state beforehand), it generates the exact same sequence of usernames, emails, event titles, and random numbers. This means:

- Event 1 always has the same `total_tickets` value (283) — the contention test invariant is stable
- The same 1,000 users are always created — `randomUserId()` in K6 (range 1–1000) always hits valid IDs
- The same 100 events are always created — `randomEventId()` in K6 (range 1–100) always hits valid IDs
- Results are reproducible — re-seeding produces the same starting state every time
