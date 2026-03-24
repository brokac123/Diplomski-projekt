# Diplomski Projekt — Performance Testing of a REST API
## Project Documentation

---

## 1. Project Overview

This project is a master's thesis on **performance testing of web applications**, focused on a REST API implementation. The subject of testing is a ticket booking system built with modern technologies, tested using industry-standard performance testing tools.

**Thesis goal:** Design, implement, and analyze performance tests (load, stress, spike, soak, breakpoint) of a REST API, compare results between local and server environments, and draw conclusions about system behavior under different traffic conditions.

---

## 2. Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API | Python 3.11 + FastAPI | REST API server |
| Database | PostgreSQL 15 | Persistent data storage |
| ORM | SQLAlchemy | Database access layer |
| Containerization | Docker + Docker Compose | Service orchestration |
| Performance Testing | K6 | Load test execution |
| Metrics Collection | Prometheus | Metrics scraping and storage |
| Visualization | Grafana | Dashboards and analysis |
| System Metrics | Node Exporter | CPU, memory, disk monitoring |

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Docker Compose                      │
│                                                      │
│  ┌──────────┐    ┌──────────┐    ┌───────────────┐  │
│  │  FastAPI │───▶│PostgreSQL│    │  Prometheus   │  │
│  │  :8000   │    │  :5432   │    │    :9090      │  │
│  └──────────┘    └──────────┘    └───────────────┘  │
│       │                                │             │
│       │ /metrics                       │             │
│       ▼                                ▼             │
│  ┌──────────┐                   ┌───────────────┐   │
│  │Prometheus│                   │    Grafana    │   │
│  │Exporter  │                   │    :3000      │   │
│  └──────────┘                   └───────────────┘   │
│                                                      │
│  ┌───────────────┐                                   │
│  │ Node Exporter │  (CPU, memory, disk metrics)      │
│  │    :9100      │                                   │
│  └───────────────┘                                   │
└─────────────────────────────────────────────────────┘
         ▲
         │ HTTP requests
┌────────────────┐
│      K6        │  (runs outside Docker)
│  Load Testing  │
└────────────────┘
```

---

## 4. Database Schema

```
┌─────────────┐         ┌─────────────────┐         ┌──────────────┐
│    users    │         │    bookings     │         │    events    │
│─────────────│         │─────────────────│         │──────────────│
│ id (PK)     │◀────────│ user_id (FK)    │────────▶│ id (PK)      │
│ username    │         │ event_id (FK)   │         │ title        │
│ email       │         │ id (PK)         │         │ location     │
│ created_at  │         │ timestamp       │         │ date         │
└─────────────┘         │ status         │         │ price        │
                        └─────────────────┘         │ total_tickets│
                                                     │available_tkt │
                                                     └──────────────┘
```

**Indexes:**
- `users`: `username`, `email`
- `events`: `title`, `location`, `date`
- `bookings`: `user_id`, `event_id`, `status`

---

## 5. API Endpoints

### Health
| Method | Endpoint | Description | Complexity |
|--------|----------|-------------|------------|
| GET | `/health` | API health check | Trivial |

### Users
| Method | Endpoint | Description | Complexity |
|--------|----------|-------------|------------|
| GET | `/users/` | List all users (paginated) | Light |
| GET | `/users/{id}` | Get single user | Light |
| POST | `/users/` | Create user | Light |
| PUT | `/users/{id}` | Full update user | Light |
| PATCH | `/users/{id}` | Partial update user | Light |
| DELETE | `/users/{id}` | Delete user (cascades bookings) | Light |
| GET | `/users/{id}/bookings` | User's bookings (paginated) | Light |

### Events
| Method | Endpoint | Description | Complexity |
|--------|----------|-------------|------------|
| GET | `/events/` | List all events (paginated) | Light |
| GET | `/events/{id}` | Get single event | Light |
| GET | `/events/upcoming` | Future events ordered by date | Medium |
| GET | `/events/search` | Filter by location, date range | Medium |
| GET | `/events/popular` | Top N events by booking count | Heavy |
| GET | `/events/{id}/stats` | Occupancy, revenue, aggregations | Heavy |
| GET | `/events/{id}/bookings` | Event's bookings (paginated) | Light |
| POST | `/events/` | Create event | Light |
| PUT | `/events/{id}` | Full update event | Light |
| PATCH | `/events/{id}` | Partial update event | Light |
| DELETE | `/events/{id}` | Delete event (cascades bookings) | Light |

### Bookings
| Method | Endpoint | Description | Complexity |
|--------|----------|-------------|------------|
| GET | `/bookings/` | List all bookings (paginated) | Light |
| GET | `/bookings/{id}` | Get single booking | Light |
| POST | `/bookings/` | Create booking (row-locked) | Medium-Write |
| PATCH | `/bookings/{id}/cancel` | Cancel booking (row-locked) | Medium-Write |
| DELETE | `/bookings/{id}` | Delete booking | Light |

### Stats
| Method | Endpoint | Description | Complexity |
|--------|----------|-------------|------------|
| GET | `/stats` | Global aggregations across all tables | Heaviest |

---

## 6. Key Technical Decisions

### Race Condition Prevention
`POST /bookings/` and `PATCH /bookings/{id}/cancel` use `SELECT FOR UPDATE` (row-level locking) to prevent concurrent requests from overselling tickets. This is critical for correctness under load testing.

### Connection Pooling
SQLAlchemy is configured with `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True` to handle concurrent load without exhausting database connections.

### Proper HTTP Status Codes
- `404` — resource not found (user, event, booking)
- `400` — invalid input (e.g. reducing tickets below booked count)
- `409 Conflict` — sold out event, or already cancelled booking

### Cascading Deletes
Deleting a user or event automatically cascades to their bookings via SQLAlchemy `cascade="all, delete-orphan"`.

---

## 7. Current State

### Completed
- [x] FastAPI application with full CRUD for Users, Events, Bookings
- [x] Heavy endpoints: `/stats`, `/events/{id}/stats`, `/events/popular`
- [x] Medium endpoints: `/events/upcoming`, `/events/search`
- [x] Write endpoints with concurrency handling: `POST /bookings/`, `PATCH /bookings/{id}/cancel`
- [x] Proper error codes (404, 400, 409)
- [x] Pagination with validation on all list endpoints (max 1000)
- [x] Database indexes on all frequently queried columns
- [x] Connection pooling configured
- [x] Docker Compose with health checks and restart policy
- [x] Prometheus metrics exposed at `/metrics`
- [x] Grafana and Node Exporter running
- [x] Seed data: 1000 users, 100 events, 2000 bookings (80% confirmed, 20% cancelled)

### Not Yet Done
- [ ] K6 test suite (see Section 8)
- [ ] K6 → Prometheus integration (push test metrics to Prometheus)
- [ ] Grafana dashboard for K6 results
- [ ] Server deployment
- [ ] Performance analysis and thesis results

---

## 8. Performance Testing Plan (K6)

All test scripts will be located in `tests/`.

### 8.1 Test Types

| Test | File | Purpose | Duration |
|------|------|---------|---------|
| Baseline | `baseline_test.js` | Establish normal behavior at low load | ~2 min |
| Load | `load_test.js` | Sustained normal + peak traffic | ~10 min |
| Stress | `stress_test.js` | Gradually increase until system breaks | ~15 min |
| Spike | `spike_test.js` | Sudden traffic burst, then recovery | ~5 min |
| Soak | `soak_test.js` | Extended duration — detect memory leaks | 30–60 min |
| Breakpoint | `breakpoint_test.js` | Slow ramp to find max capacity | ~30 min |

### 8.2 Test Scenarios

Each test will simulate realistic traffic distribution:
- 40% — light read endpoints (`GET /events/`, `GET /events/{id}`)
- 20% — medium endpoints (`GET /events/upcoming`, `GET /events/search`)
- 15% — write operations (`POST /bookings/`, `PATCH /bookings/{id}/cancel`)
- 15% — heavy endpoints (`GET /events/{id}/stats`, `GET /events/popular`)
- 10% — heaviest endpoint (`GET /stats`)

### 8.3 Thresholds (Pass/Fail Criteria)

```
http_req_duration p(95) < 500ms
http_req_duration p(99) < 1000ms
http_req_failed rate < 1%
```

### 8.4 Custom Metrics
- `booking_success_rate` — successful bookings per second
- `booking_failure_rate` — failed bookings (sold out vs. invalid)

---

## 9. Monitoring

### Prometheus
- Scrapes API metrics every 5 seconds from `http://api:8000/metrics`
- Scrapes system metrics from Node Exporter every 5 seconds
- Access: `http://localhost:9090`

### Grafana
- Access: `http://localhost:3000` (default credentials: admin/admin)
- **To be configured:** K6 dashboard showing RPS, latency percentiles, error rate, active VUs

### K6 → Prometheus Integration (planned)
K6 will push test metrics to Prometheus via Remote Write, enabling real-time test visibility in Grafana during test execution.

---

## 10. Running the Project

See [README.md](README.md).

---

## 11. Project Roadmap

### Phase 1 — API & Infrastructure ✅ DONE
Fix race conditions, add indexes, connection pooling, Docker health checks, remove dev flags.

### Phase 2 — API Improvements ✅ DONE
Add new endpoints (stats, upcoming, search, popular, cancel), fix error codes, improve schema, update seed data.

### Phase 3 — K6 Test Suite 🔄 IN PROGRESS
Write all 6 test types with proper thresholds, custom metrics, and realistic traffic distribution.

### Phase 4 — Monitoring & Dashboards ⏳ PLANNED
Configure K6 → Prometheus integration, build Grafana dashboard for test results.

### Phase 5 — Server Deployment ⏳ PLANNED
Deploy to remote server, re-run all tests, compare local vs. server results.

### Phase 6 — Analysis & Thesis ⏳ PLANNED
Analyze results, identify bottlenecks, draw conclusions, write thesis.
