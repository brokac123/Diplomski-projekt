# Diplomski Projekt — Performance Testing of a REST API
## Project Documentation

---

## 1. Project Overview

This project is a master's thesis on **performance testing of web applications**, focused on a REST API implementation. The subject of testing is a ticket booking system built with modern technologies, tested using industry-standard performance testing tools.

**Thesis goal:** Design, implement, and analyze performance tests (load, stress, spike, soak, breakpoint) of a REST API, compare results between different worker configurations, and draw conclusions about system behavior under different traffic conditions.

---

## 2. Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API | Python 3.11 + FastAPI | REST API server |
| ASGI Server | Uvicorn | Serves FastAPI (1 or 4 workers) |
| Database | PostgreSQL 15 | Persistent data storage |
| ORM | SQLAlchemy | Database access layer |
| Containerization | Docker + Docker Compose | Service orchestration |
| Performance Testing | K6 | Load test execution |
| Metrics Collection | Prometheus | Metrics scraping and storage |
| Visualization | Grafana | Dashboards and analysis |
| System Metrics | Node Exporter | CPU, memory monitoring |

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
│  │ Node Exporter │  (CPU, memory metrics)            │
│  │    :9100      │                                   │
│  └───────────────┘                                   │
└─────────────────────────────────────────────────────┘
         ▲
         │ HTTP requests + Prometheus Remote Write
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

### K6 Expected Response Codes
K6 is configured via `http.setResponseCallback(http.expectedStatuses(200, 404, 409))` in `tests/helpers.js` to treat `404` and `409` as expected business responses rather than HTTP failures. Without this, sold-out events (409) and not-found lookups (404) would be counted as errors, skewing the `http_req_failed` metric.

---

## 7. Performance Test Suite

All test scripts are located in `tests/`.

### 7.1 Test Architecture

```
tests/
├── helpers.js               # Shared utilities (BASE_URL, random IDs, expected status codes)
├── baseline_test.js         # Phase A: Smoke test
├── endpoint_benchmark_test.js # Phase A: Per-endpoint isolation
├── realistic_test.js        # Traffic generator module (imported by Phase B tests)
├── load_test.js             # Phase B: Normal sustained load
├── stress_test.js           # Phase B: Gradual overload
├── spike_test.js            # Phase B: Sudden traffic burst
├── soak_test.js             # Phase B: Long-duration stability
├── breakpoint_test.js       # Phase B: Find max capacity
├── contention_test.js       # Phase C: Row-level locking under pressure
└── read_vs_write_test.js    # Phase C: Read-heavy vs write-heavy comparison
```

**helpers.js** provides shared configuration used by all tests:
- `BASE_URL` — API base URL (`http://localhost:8000`)
- Random ID generators for users (1-1000), events (1-100), bookings (1-2000)
- Random location picker (8 Croatian cities)
- Expected HTTP status codes (200, 404, 409)
- `checkApiHealth()` — verifies API is alive before test starts (used in `setup()`)
- `saveSummary(data, testName)` — saves terminal output + JSON results to `results/<workers>/<testName>.json`
- `WORKERS` label — reads `-e WORKERS=` env var (default: `1w`) to organize results by worker config

**realistic_test.js** exports a `trafficMix()` function that simulates realistic booking platform usage with weighted random selection:
- 25% browse events, 15% view single event, 10% search events
- 8% upcoming events, 10% list users, 5% user bookings
- 12% create booking, 5% cancel booking
- 5% event stats, 3% popular events, 2% global stats

### 7.2 Phase A — Baseline & Endpoint Benchmark

| Test | File | VUs | Duration | Purpose |
|------|------|-----|----------|---------|
| Baseline (Smoke) | `baseline_test.js` | 10 | 30s | Verify all endpoints work under minimal load |
| Endpoint Benchmark | `endpoint_benchmark_test.js` | 20 each | 5 x 1min | Isolate per-endpoint performance without interference |

**Endpoint Benchmark** runs 5 sequential scenarios with `startTime` offsets:
1. `light_reads` (0s) — health, user, event, booking by ID
2. `list_reads` (70s) — list users, events, bookings with limit=100
3. `search_filter` (140s) — search, upcoming, user bookings, event bookings
4. `writes` (210s) — create booking, cancel booking
5. `heavy_aggregations` (280s) — event stats, popular events, global stats

### 7.3 Phase B — Standard Performance Test Types

All Phase B tests import `trafficMix()` from `realistic_test.js` for consistent traffic patterns.

| Test | File | Config | Duration | Purpose |
|------|------|--------|----------|---------|
| Load | `load_test.js` | 0→50 VUs, hold, ramp down | ~8 min | Sustained normal traffic — baseline performance |
| Stress | `stress_test.js` | 0→50→100→200→300→0 VUs | ~8 min | Gradual overload — find degradation point |
| Spike | `spike_test.js` | 10→300 VUs in 10s, then back | ~3.5 min | Sudden burst — test recovery behavior |
| Soak | `soak_test.js` | 30 VUs for 30 min | ~32 min | Long duration — detect memory leaks, latency creep |
| Breakpoint | `breakpoint_test.js` | 10→500 RPS, open model | ~20 min | Find maximum capacity (aborts when p95 > 5s) |

**Key differences between tests:**
- **Load vs Stress:** Load tests normal capacity; stress pushes beyond limits
- **Stress vs Spike:** Stress ramps gradually; spike is a sudden jump — tests different failure modes
- **Closed vs Open model:** Load/stress/spike/soak use closed model (VUs wait for response). Breakpoint uses open model (requests arrive regardless of response) — more realistic for real-world traffic
- **Soak:** Specifically designed to find time-dependent issues (memory leaks, connection pool exhaustion) that only appear after extended running

### 7.4 Phase C — Targeted Scenarios

| Test | File | Config | Duration | Purpose |
|------|------|--------|----------|---------|
| Contention | `contention_test.js` | 50 VUs, same event | 2 min | Test `SELECT FOR UPDATE` row locking correctness |
| Read vs Write | `read_vs_write_test.js` | 30 VUs each scenario | ~6 min | Compare read-heavy (90/10) vs write-heavy (40/60) workloads |

### 7.5 Thresholds (Pass/Fail Criteria)

Each test has specific thresholds appropriate to the load level:

| Test | p(95) Threshold | Error Rate Threshold |
|------|----------------|---------------------|
| Baseline | < 300ms | < 1% |
| Load | < 500ms, p(99) < 1000ms | < 1% |
| Stress | < 1500ms | < 10% |
| Spike | < 2000ms | < 15% |
| Soak | < 700ms | < 1% |
| Breakpoint | < 5000ms (abortOnFail) | — |
| Contention | Booking latency < 3000ms | < 5% |
| Read vs Write | Read < 500ms, Write < 1500ms | < 5% |

### 7.6 Custom Metrics

Tests track business-level metrics beyond standard HTTP metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `booking_success` | Counter | Successful booking creations |
| `booking_fail` | Counter | Failed booking attempts (errors) |
| `booking_sold_out` | Counter | Bookings rejected — event sold out (409) |
| `contention_booking_success` | Counter | Successful bookings in contention test |
| `contention_booking_sold_out` | Counter | Sold-out responses in contention test |
| `contention_booking_latency` | Trend | Booking endpoint latency under contention |
| `read_heavy_bookings` | Counter | Bookings created in read-heavy scenario |
| `write_heavy_bookings` | Counter | Bookings created in write-heavy scenario |

---

## 8. Monitoring & Visualization

### 8.1 Monitoring Stack

| Service | URL | Purpose |
|---------|-----|---------|
| Prometheus | http://localhost:9090 | Metrics storage — scrapes API + Node Exporter, receives K6 remote write |
| Grafana | http://localhost:3000 | Dashboard visualization (login: admin/admin) |
| Node Exporter | http://localhost:9100 | Host system metrics (CPU, memory) |
| API Metrics | http://localhost:8000/metrics | FastAPI Prometheus endpoint |

### 8.2 Data Flow

```
K6 test run ──(Prometheus Remote Write)──▶ Prometheus ──▶ Grafana Dashboard
                                               ▲
Node Exporter ──(scrape every 5s)──────────────┘
API /metrics ──(scrape every 5s)───────────────┘
```

K6 pushes test metrics directly to Prometheus via remote write during test execution. Prometheus also scrapes the API and Node Exporter every 5 seconds. Grafana reads from Prometheus to display all metrics on one dashboard.

### 8.3 How Metrics Are Collected — K6 Metric Types

K6 internally tracks four types of metrics, each sent to Prometheus differently:

| K6 Metric Type | Examples | How It's Sent to Prometheus |
|----------------|----------|---------------------------|
| **Counter** | `http_reqs`, `booking_success`, `booking_fail` | Sent automatically as cumulative totals (e.g., `k6_http_reqs_total`) |
| **Rate** | `http_req_failed` | Sent automatically as a ratio 0-1 (e.g., `k6_http_req_failed_rate`) |
| **Gauge** | `vus`, `vus_max` | Sent automatically as current value (e.g., `k6_vus`) |
| **Trend** | `http_req_duration` | **Requires explicit configuration** — see below |

**Counters, Rates, and Gauges** are sent automatically via Prometheus remote write — no extra configuration needed.

**Trends** are the exception. A Trend collects every individual measurement (e.g., every request's response time) and K6 must decide which summary statistics to compute and send. By default, K6 only sends **p99**. The environment variable `K6_PROMETHEUS_RW_TREND_STATS` controls which stats are sent:

```
K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max"
```

This causes each Trend metric to generate multiple Prometheus gauges:
- `k6_http_req_duration_p50`, `k6_http_req_duration_p90`, `k6_http_req_duration_p95`, `k6_http_req_duration_p99`
- `k6_http_req_duration_avg`, `k6_http_req_duration_min`, `k6_http_req_duration_max`

**Note:** K6 sends duration values in **seconds** (e.g., 0.076 = 76ms). The Grafana dashboard queries multiply by 1000 to display in milliseconds.

### 8.4 Three Data Paths into Prometheus

| Source | Transport | Frequency | Dashboard Panels |
|--------|-----------|-----------|-----------------|
| **K6** (test metrics) | Push via remote write | Real-time during test | VUs, RPS, Response Times, Error Rate, Booking Metrics |
| **Node Exporter** (system metrics) | Pull via Prometheus scrape | Every 5 seconds | CPU Usage, Memory Usage |
| **FastAPI /metrics** (app metrics) | Pull via Prometheus scrape | Every 5 seconds | Available but not used on dashboard (K6 metrics are more detailed) |

All three paths feed into the same Prometheus instance. Grafana reads from that single Prometheus to display everything on one dashboard.

### 8.5 Grafana Dashboard — "K6 Performance Test Results"


Location: Dashboards → K6 → K6 Performance Test Results

The dashboard contains **13 panels** organized in 3 categories:

#### Application Performance Metrics (from K6)

| Panel | Metric Source | What It Shows | Why It Matters |
|-------|--------------|---------------|----------------|
| **Active Virtual Users** | `k6_vus` | Number of concurrent virtual users over time | Shows the load profile — essential for correlating "latency spiked when VUs hit X" |
| **Requests Per Second (RPS)** | `rate(k6_http_reqs_total)` | Total throughput over time | If VUs increase but RPS flattens, the system is saturated |
| **Response Time Percentiles** | `k6_http_req_duration_p50/p90/p95/p99` | p50 (typical), p90, p95, p99 latency in ms | The most important performance metric. p95 = what 95% of users experience. Thesis thresholds are based on these |
| **Error Rate** | `k6_http_req_failed_rate` | Percentage of failed HTTP requests | Indicates system reliability — are requests failing under load? |
| **RPS by Endpoint** | `rate(k6_http_reqs_total) by name` | Throughput per individual endpoint | Shows traffic distribution — validates the weighted traffic mix |
| **Response Time by Endpoint** | `k6_http_req_duration_p95 by name` | p95 latency per endpoint | Identifies bottleneck endpoints — which operations are slowest? |
| **Response Time vs Virtual Users** | `k6_http_req_duration + k6_vus` | Dual-axis: latency (left) vs VUs (right) | The key thesis chart — shows exactly when latency degrades as load increases |

#### Business Metrics (from K6 Custom Counters)

| Panel | Metric Source | What It Shows | Why It Matters |
|-------|--------------|---------------|----------------|
| **Booking Metrics** | `k6_booking_success_total` | Total successful bookings | Proves the system correctly processes business operations under load |
| **Sold Out Responses** | `k6_booking_sold_out_total` | Total 409 sold-out responses | Expected behavior — shows capacity limits working correctly |
| **Failed Bookings** | `k6_booking_fail_total` | Total booking errors | Should be 0 — any failures indicate bugs |
| **HTTP Requests Total** | `k6_http_reqs_total` | Total request volume | Summary of test scope |
| **Avg Response Time** | `k6_http_req_duration_avg` | Gauge showing current average | Quick at-a-glance health indicator |
| **Peak VUs** | `max_over_time(k6_vus)` | Maximum concurrent users reached | Summary stat for test reports |

#### System Resource Metrics (from Node Exporter)

| Panel | Metric Source | What It Shows | Why It Matters |
|-------|--------------|---------------|----------------|
| **CPU Usage (%)** | `node_cpu_seconds_total` | Host CPU utilization percentage | Answers "why did performance degrade?" — CPU saturation? |
| **Memory Usage** | `node_memory_MemTotal/MemAvailable` | Used vs total memory | Detects memory leaks (soak test) and exhaustion (stress test) |

**Note:** Node Exporter monitors the WSL2 VM (Docker's Linux layer on Windows), which is allocated half of host RAM by default. This accurately reflects the resources available to the API and PostgreSQL containers.

### 8.6 Metrics Selection Rationale

The 13 panels cover the **three pillars of performance testing**:

1. **How fast?** — Response time percentiles, avg, per-endpoint breakdown
2. **How reliable?** — Error rate, booking success/fail/sold-out
3. **How much?** — RPS, VUs, total requests, CPU/memory utilization

These align with Google's **Four Golden Signals** for monitoring:
- **Latency** — response time percentiles
- **Traffic** — RPS, total requests
- **Errors** — error rate, failed bookings
- **Saturation** — CPU usage, memory usage, VUs vs response time correlation

**Excluded metrics** (available but not needed):
- `k6_http_req_blocked` — K6 internal TCP wait, not API performance
- `k6_http_req_connecting` — TCP handshake time, network-level
- `k6_http_req_tls_handshaking` — not applicable (HTTP, not HTTPS)
- `k6_http_req_sending/receiving` — network transfer, usually negligible
- `k6_data_sent/received` — payload size, not relevant to performance
- Node Exporter disk I/O — dataset fits in memory, disk not a bottleneck
- Node Exporter network — all traffic is local (K6 → Docker)

---

## 9. How to Run Performance Tests

### 9.1 Prerequisites

Ensure all services are running:
```bash
docker compose up --build -d
docker compose ps          # verify all services are healthy
```

Service URLs to verify:
- API: http://localhost:8000/health
- Prometheus: http://localhost:9090/targets (API and Node Exporter should show "UP")
- Grafana: http://localhost:3000 (login: admin/admin)

### 9.2 Test Execution Workflow

**For each test, follow these steps:**

#### Step 1 — Re-seed the database
Re-seed before each test to ensure consistent starting conditions (1000 users, 100 events, 2000 bookings):
```bash
docker compose exec api python seed_data.py --reset
```

#### Step 2 — Run the test with Prometheus output

**1-worker mode (default):**

PowerShell:
```powershell
$env:K6_PROMETHEUS_RW_SERVER_URL="http://localhost:9090/api/v1/write"; $env:K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max"; k6 run --out experimental-prometheus-rw tests/<test_file>.js
```

Git Bash:
```bash
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max" k6 run --out experimental-prometheus-rw tests/<test_file>.js
```

**4-worker mode** — add `-e WORKERS=4w` so results are saved to `results/4w/`:

PowerShell:
```powershell
$env:K6_PROMETHEUS_RW_SERVER_URL="http://localhost:9090/api/v1/write"; $env:K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max"; k6 run --out experimental-prometheus-rw -e WORKERS=4w tests/<test_file>.js
```

Git Bash:
```bash
K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max" k6 run --out experimental-prometheus-rw -e WORKERS=4w tests/<test_file>.js
```

The environment variables:
- `K6_PROMETHEUS_RW_SERVER_URL` — tells K6 where to push metrics (Prometheus remote write endpoint)
- `K6_PROMETHEUS_RW_TREND_STATS` — tells K6 which percentile gauges to send (default only sends p99)
- `-e WORKERS=4w` — labels output files with worker config (default: `1w`). Results saved to `results/1w/` or `results/4w/`

**Result files:** Each test auto-saves a JSON summary to `results/<workers>/<test_name>.json` (e.g., `results/1w/load_test.json`). Terminal output remains unchanged.

#### Step 3 — View results in Grafana
1. Open http://localhost:3000 → Dashboards → K6 → K6 Performance Test Results
2. Set time range to cover the test duration (e.g., "Last 15 minutes" for an 8 min test)
3. Set auto-refresh to 5s for live monitoring during test execution
4. Take screenshots for thesis documentation (use Windows + Shift + S)

#### Step 4 — Restart API if it crashed
After high-load tests (stress, spike, breakpoint), the API container may become unresponsive:
```bash
docker compose restart api
```

Verify recovery:
```bash
docker compose ps              # check health status
curl http://localhost:8000/health  # verify API responds
```

### 9.3 Recommended Test Execution Order

Run tests in this order, as each builds on insights from the previous:

| # | Test | Command | Duration | Re-seed? | May crash API? |
|---|------|---------|----------|----------|----------------|
| 1 | Baseline | `tests/baseline_test.js` | 30s | Yes | No |
| 2 | Endpoint Benchmark | `tests/endpoint_benchmark_test.js` | ~6 min | No | No |
| 3 | Load | `tests/load_test.js` | ~8 min | Yes | No |
| 4 | Stress | `tests/stress_test.js` | ~8 min | Yes | Yes |
| 5 | Spike | `tests/spike_test.js` | ~3.5 min | No | Yes |
| 6 | Soak | `tests/soak_test.js` | ~32 min | Yes | No |
| 7 | Breakpoint | `tests/breakpoint_test.js` | ~2-20 min | Yes | Yes |
| 8 | Contention | `tests/contention_test.js` | 2 min | Yes | No |
| 9 | Read vs Write | `tests/read_vs_write_test.js` | ~6 min | Yes | No |

**Important notes:**
- Always re-seed before tests that create bookings to avoid skewed results from sold-out events
- After tests marked "May crash API", run `docker compose restart api` before the next test
- The breakpoint test aborts automatically when p(95) exceeds 5 seconds — this is by design
- Prometheus stores all data, so overlapping test results will appear on the same dashboard. Use the time picker to zoom into specific test windows

### 9.4 Running Tests Without Grafana

For quick iteration or terminal-only results, run without the Prometheus output:
```bash
k6 run tests/load_test.js
```

This still shows full results in the terminal but won't push metrics to Grafana.

---

## 10. Worker Configuration Comparison

### 10.1 Purpose

Compare API performance with **1 Uvicorn worker** (default) vs **4 Uvicorn workers** to analyze the impact of horizontal scaling within a single container. This is a key thesis comparison.

### 10.2 Switching Between Configurations

**1 worker (default):** No changes needed — the Dockerfile uses the default Uvicorn command.

**4 workers:** Uncomment the command override in `docker-compose.yml`:
```yaml
api:
  build: .
  ports:
    - "8000:8000"
  # Uncomment the line below for 4-worker mode (thesis comparison):
  command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

Then rebuild and restart:
```bash
docker compose up --build -d
docker compose exec api python seed_data.py --reset
```

When running tests in 4-worker mode, add `-e WORKERS=4w` to save results separately:
```powershell
$env:K6_PROMETHEUS_RW_SERVER_URL="http://localhost:9090/api/v1/write"; $env:K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max"; k6 run --out experimental-prometheus-rw -e WORKERS=4w tests/<test_file>.js
```

This saves JSON results to `results/4w/` instead of `results/1w/`, keeping both sets side-by-side for comparison.

### 10.3 What to Compare

Re-run key tests with 4 workers and compare:
- Response time percentiles (p50, p95, p99)
- Maximum throughput (RPS)
- Error rate under stress
- Breakpoint (max RPS before collapse)
- CPU utilization (4 workers should use more CPU cores)
- Whether API crashes under stress/spike tests

---

## 11. Key Technical Decisions

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

## 12. Project File Structure

```
Diplomski projekt/
├── app/
│   ├── main.py              # FastAPI app — all REST endpoints
│   ├── models.py            # SQLAlchemy models (User, Event, Booking)
│   ├── schemas.py           # Pydantic schemas
│   ├── crud.py              # Database operations
│   └── database.py          # DB connection (SessionLocal, Base, get_db)
├── tests/
│   ├── helpers.js           # Shared K6 utilities
│   ├── baseline_test.js     # Smoke test
│   ├── endpoint_benchmark_test.js  # Per-endpoint isolation
│   ├── realistic_test.js    # Traffic generator module
│   ├── load_test.js         # Sustained load test
│   ├── stress_test.js       # Gradual overload test
│   ├── spike_test.js        # Sudden burst test
│   ├── soak_test.js         # Long-duration stability test
│   ├── breakpoint_test.js   # Max capacity finder
│   ├── contention_test.js   # Row-locking test
│   └── read_vs_write_test.js # Workload comparison
├── monitoring/
│   ├── prometheus.yml       # Prometheus config
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources.yml  # Auto-configure Prometheus datasource
│       │   └── dashboards.yml   # Auto-load dashboard files
│       └── dashboards/
│           └── k6_results.json  # K6 Performance Test Results dashboard (13 panels)
├── results/
│   ├── 1w/                   # Auto-saved JSON results for 1-worker tests
│   ├── 4w/                   # Auto-saved JSON results for 4-worker tests
│   └── 1_worker_results.md   # Test results with 1 Uvicorn worker
├── docker-compose.yml       # All services
├── Dockerfile               # Python container
├── seed_data.py             # Faker-based seeding (1000 users, 100 events, 2000 bookings)
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables
├── .dockerignore            # Docker build exclusions
├── documentation.md         # This file
└── README.md                # Quick start guide
```

---

## 13. Project Roadmap

### Phase 1 — API & Infrastructure ✅ DONE
Fix race conditions, add indexes, connection pooling, Docker health checks, remove dev flags.

### Phase 2 — API Improvements ✅ DONE
Add new endpoints (stats, upcoming, search, popular, cancel), fix error codes, improve schema, update seed data.

### Phase 3 — K6 Test Suite ✅ DONE
9 test types implemented: baseline, endpoint benchmark, load, stress, spike, soak, breakpoint, contention, read vs write. Realistic traffic distribution, custom booking metrics, per-endpoint tagging.

### Phase 4 — Monitoring & Dashboards ✅ DONE
K6 → Prometheus remote write integration. Grafana dashboard with 13 panels covering application metrics (K6), business metrics (booking counters), and system resources (Node Exporter CPU/memory).

### Phase 5 — 1-Worker Test Execution ✅ DONE
All 9 tests executed with 1 Uvicorn worker. Results documented in `results/1_worker_results.md`.

### Phase 6 — 4-Worker Comparison 🔄 IN PROGRESS
Re-run key tests with 4 Uvicorn workers. Compare results with 1-worker baseline.

### Phase 7 — Analysis & Thesis ⏳ PLANNED
Analyze results, identify bottlenecks, draw conclusions, write thesis.
