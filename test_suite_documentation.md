# Test Suite Documentation

This document explains the complete K6 load testing suite — every file, its purpose, its load profile, its thresholds, and how all the pieces connect. It covers the architecture of the test suite (how shared code is organized), the three test phases, and what each test is designed to prove or measure.

---

## Table of Contents

1. [Overview — The Test Suite Structure](#1-overview--the-test-suite-structure)
2. [helpers.js — Shared Utilities](#2-helpersjs--shared-utilities)
3. [realistic_test.js — Traffic Definition and Smoke Test](#3-realistic_testjs--traffic-definition-and-smoke-test)
4. [Phase A — Characterization Tests](#4-phase-a--characterization-tests)
   - [baseline_test.js](#41-baseline_testjs)
   - [endpoint_benchmark_test.js](#42-endpoint_benchmark_testjs)
5. [Phase B — Load Scaling Tests](#5-phase-b--load-scaling-tests)
   - [load_test.js](#51-load_testjs)
   - [stress_test.js](#52-stress_testjs)
   - [spike_test.js](#53-spike_testjs)
   - [soak_test.js](#54-soak_testjs)
   - [breakpoint_test.js](#55-breakpoint_testjs)
6. [Phase C — Behavioral Tests](#6-phase-c--behavioral-tests)
   - [contention_test.js](#61-contention_testjs)
   - [read_vs_write_test.js](#62-read_vs_write_testjs)
   - [recovery_test.js](#63-recovery_testjs)
7. [How Tests Share Code](#7-how-tests-share-code)
8. [K6 Executors Used](#8-k6-executors-used)
9. [Thresholds and Pass/Fail Logic](#9-thresholds-and-passfail-logic)
10. [Output Files and Result Structure](#10-output-files-and-result-structure)
11. [How to Run Tests](#11-how-to-run-tests)

---

## 1. Overview — The Test Suite Structure

The test suite contains 12 JavaScript files. Two are infrastructure (shared utilities and traffic definition). The remaining 10 are individual test scenarios organized into three phases.

```
tests/
├── helpers.js                  — Shared utilities (BASE_URL, random IDs, saveSummary, etc.)
├── realistic_test.js           — Traffic mix definition (trafficMix) + standalone smoke test
│
├── baseline_test.js            — Phase A: Smoke test, endpoint coverage check
├── endpoint_benchmark_test.js  — Phase A: Per-endpoint latency isolation
│
├── load_test.js                — Phase B: Normal + peak load validation
├── stress_test.js              — Phase B: Progressive overload, degradation point
├── spike_test.js               — Phase B: Sudden traffic burst behavior
├── soak_test.js                — Phase B: Long-duration stability (memory leaks, drift)
├── breakpoint_test.js          — Phase B: Absolute throughput ceiling (RPS-controlled)
│
├── contention_test.js          — Phase C: PostgreSQL row-level lock behavior
├── read_vs_write_test.js       — Phase C: Read-heavy vs write-heavy traffic comparison
└── recovery_test.js            — Phase C: Post-overload recovery measurement
```

**The key architectural decision:** All Phase B tests and the recovery test import and call a single shared function — `trafficMix()` from `realistic_test.js`. The traffic shape (what requests are made and in what proportion) is identical across all of these tests. What varies is the load profile — how many VUs, how they ramp, and for how long. This ensures all cross-config comparisons (1w vs 2w vs 4w) are apples-to-apples.

---

## 2. helpers.js — Shared Utilities

`helpers.js` is imported by every test file. It provides all shared configuration, data generation, and output logic so that each test file only needs to define its own load profile.

### Exports

| Export | Type | Purpose |
|--------|------|---------|
| `BASE_URL` | `string` | API base URL. Defaults to `http://localhost:8000`. Override with `-e BASE_URL=...` |
| `JSON_HEADERS` | `object` | `{ headers: { "Content-Type": "application/json" } }` — used in POST requests |
| `LOCATIONS` | `string[]` | 8 Croatian city names used for location-based event search |
| `randomInt(min, max)` | `function` | Returns a random integer in `[min, max]` inclusive |
| `randomUserId()` | `function` | Returns a random user ID in `[1, 1000]` (matches seed data: 1000 users) |
| `randomEventId()` | `function` | Returns a random event ID in `[1, 100]` (matches seed data: 100 events) |
| `randomBookingId()` | `function` | Returns a random booking ID in `[1, 2000]` (covers seeded + test-generated bookings) |
| `randomLocation()` | `function` | Returns a random city from `LOCATIONS` |
| `randomSleep(min, max)` | `function` | Returns a random float in `[min, max]` for use as a `sleep()` argument |
| `checkApiHealth()` | `function` | GETs `/health`, throws if not 200 — used as the `setup()` function in every test |
| `configureExpectedStatuses(...statuses)` | `function` | Calls `http.setResponseCallback` so K6 does not count expected non-200 codes (e.g., 404, 409) as failures |
| `saveSummary(data, testName)` | `function` | Writes JSON result file to `results/{WORKERS}/{testName}.json` and prints terminal summary |

### The WORKERS variable

```js
const WORKERS = __ENV.WORKERS || "1w";
```

Every test result is saved to `results/{WORKERS}/{testName}.json`. Setting `-e WORKERS=4w` at run time redirects output to the `4w/` folder. This is how the same 10 test scripts produce separate result sets for each worker configuration without any code changes.

### configureExpectedStatuses

```js
configureExpectedStatuses(200, 404, 409);
```

This call appears at the top of every test file. It tells K6 that 404 (booking not found) and 409 (event sold out) are expected, non-failure responses. Without this, K6 would count sold-out booking attempts as HTTP errors, inflating the `http_req_failed` metric and incorrectly failing thresholds.

---

## 3. realistic_test.js — Traffic Definition and Smoke Test

`realistic_test.js` serves two roles:

1. **Defines the shared `trafficMix()` function** — the single source of truth for what traffic looks like across all Phase B tests and the recovery test.
2. **Is itself a runnable standalone smoke test** — 20 VUs, 1 minute, with `sleep(0.5–2.0s)` between iterations.

### Traffic Distribution

```
25% — Browse events list         GET /events/?limit=20
15% — View single event          GET /events/{id}
10% — Search events by location  GET /events/search?location=...
 8% — Upcoming events            GET /events/upcoming?limit=20
10% — List users                 GET /users/?limit=20
 5% — View user bookings         GET /users/{id}/bookings?limit=20
12% — Create booking             POST /bookings/
 5% — Cancel booking             PATCH /bookings/{id}/cancel
 5% — Event stats                GET /events/{id}/stats
 3% — Popular events             GET /events/popular?limit=10
 2% — Global stats               GET /stats
```

**Read/write split:** 83% reads, 17% writes. This reflects realistic booking platform behavior — most users browse; only a fraction actively books or cancels.

**Why this matters for the thesis:** Because `trafficMix()` is shared, all cross-config scaling comparisons use identical traffic. The worker count is the only independent variable.

### Standalone options

```js
vus: 20, duration: "1m"
```

Thresholds: `p(95)<500ms`, `http_req_failed<1%`, `checks>95%`

This is the gentlest test in the suite — used to verify that the system is generally healthy before running heavier scenarios.

### Custom metrics exported

| Metric | Type | Tracks |
|--------|------|--------|
| `booking_success` | Counter | HTTP 200 responses to POST /bookings/ |
| `booking_fail` | Counter | Unexpected non-200, non-409 responses to POST /bookings/ |
| `booking_sold_out` | Counter | HTTP 409 responses to POST /bookings/ (expected, not an error) |

These three metrics are re-exported by every Phase B test that imports `trafficMix`, so they appear in all result files.

---

## 4. Phase A — Characterization Tests

Phase A tests run before the scaling experiments. Their job is to characterize the system under normal, non-saturating conditions and establish a performance baseline per endpoint.

### 4.1 baseline_test.js

**Purpose:** Verify that every endpoint is reachable and returns correct responses before heavy tests begin. If this test fails, no other test should be run.

**Load profile:** 10 VUs, 30 seconds. Every VU hits every endpoint category in sequence (not random traffic mix).

**Endpoints covered:**
- `GET /health` — with body assertion (`status === "ok"`)
- `GET /users/`, `GET /users/{id}`, `GET /users/{id}/bookings`
- `GET /events/`, `GET /events/{id}`, `GET /events/upcoming`, `GET /events/search`, `GET /events/popular`, `GET /events/{id}/stats`, `GET /events/{id}/bookings`
- `GET /bookings/`, `GET /bookings/{id}`
- `GET /stats` — with field assertion (`total_users !== undefined`)

**Thresholds:**
| Threshold | Value | Reasoning |
|-----------|-------|-----------|
| `p(95)<300ms` | 300ms | Very strict — at 10 VUs the system should be idle |
| `http_req_failed<1%` | 1% | Near-zero tolerance |
| `checks>99%` | 99% | Almost every assertion must pass |

**Key difference from other tests:** This is the only test that hits every endpoint explicitly in a fixed sequence rather than using `trafficMix()`. It is a correctness check, not a performance measurement.

---

### 4.2 endpoint_benchmark_test.js

**Purpose:** Isolate each endpoint category under controlled load to measure per-category latency independently. Runs 5 sequential scenarios (non-overlapping via `startTime` offsets), each 1 minute at 20 VUs.

**Duration:** ~8.5 minutes total (5 × 60s + 4 × 100s gaps).

**Scenarios:**

| Scenario | startTime | Endpoints | What it measures |
|----------|-----------|-----------|-----------------|
| `light_reads` | 0s | `/health`, `/users/{id}`, `/events/{id}`, `/bookings/{id}` | Primary key lookups — fastest possible reads |
| `list_reads` | 100s | `/users/?limit=100`, `/events/?limit=100`, `/bookings/?limit=100` | Paginated full-table scans |
| `search_filter` | 200s | `/events/search`, `/events/upcoming`, `/users/{id}/bookings`, `/events/{id}/bookings` | Filtered queries and joins |
| `writes` | 300s | `POST /bookings/`, `PATCH /bookings/{id}/cancel` | Write operations with row-level locking |
| `heavy_aggregations` | 400s | `/events/{id}/stats`, `/events/popular`, `/stats` | JOINs, GROUP BY, subqueries — most expensive reads |

**Per-scenario thresholds:**
| Scenario | p(95) threshold | Reasoning |
|----------|----------------|-----------|
| `light_reads` | 200ms | PK lookups should always be fast |
| `list_reads` | 500ms | Larger payloads, more DB work |
| `search_filter` | 500ms | Filtered queries with joins |
| `writes` | 1000ms | Row locking adds latency |
| `heavy_aggregations` | 1500ms | Most expensive operations |

**Why sequential scenarios?** Overlapping them would mix endpoint types in the metrics, making per-category isolation impossible. The 100s gap (60s duration + 30s gracefulStop + 10s buffer) guarantees clean separation.

---

## 5. Phase B — Load Scaling Tests

Phase B is the core of the thesis experiment. All five tests use the same `trafficMix()` function and are run three times — once per worker configuration (1w, 2w, 4w). Results are compared across configs to demonstrate linear scaling behavior.

**Shared pattern:**
```js
import { trafficMix } from "./realistic_test.js";

export default function () {
  trafficMix();
  sleep(...);
}
```

### 5.1 load_test.js

**Purpose:** Validate that the system meets performance SLAs under expected normal and peak load. This is the "everything should be fine" test — no config should struggle here.

**Load profile:**
```
2m ramp 0→50 VUs
5m hold at 50 VUs   (steady state)
1m ramp 50→0 VUs
```

**Think time:** `randomSleep(0.5, 2.0)` — realistic user pacing.

**Thresholds:**
| Threshold | Value |
|-----------|-------|
| `p(95)<500ms` | Comfortable SLA |
| `p(99)<1000ms` | Hard ceiling |
| `http_req_failed<1%` | Near-zero errors |
| `checks>95%` | Strong correctness |

**Expected result across configs:** All three configs (1w, 2w, 4w) produce nearly identical results at 50 VUs. No config is saturated. This is by design — the test proves correctness and establishes that extra workers introduce no overhead at low load.

---

### 5.2 stress_test.js

**Purpose:** Progressively increase load beyond normal capacity to find where each config degrades. This is the **primary scaling proof test** — the most reliable and consistent measurement across all runs.

**Load profile:**
```
1m ramp 0→50 VUs    (warm up)
2m hold at 100 VUs  (normal load)
2m hold at 200 VUs  (above normal)
2m hold at 300 VUs  (stress level)
1m ramp 300→0 VUs
```

**Think time:** `sleep(0.5)` — fixed, shorter than load test. At 300 VUs with 0.5s sleep, every worker's event loop is fully saturated.

**Thresholds:**
| Threshold | Value | Reasoning |
|-----------|-------|-----------|
| `p(95)<1500ms` | Relaxed | We expect degradation — this is not a pass/fail measurement |
| `http_req_failed<10%` | 10% | Allows for some errors at peak |
| `checks>90%` | 90% | Degraded but functional |

**Why this is the most reliable scaling test:** It uses a closed-model executor (constant-vus). VU count is fixed regardless of response time. At 300 VUs all event loops are saturated simultaneously and for a sustained period, making the CPU bottleneck the dominant factor. Scheduling jitter matters less because the load is sustained, not bursty.

**Expected result:** Clear linear ordering — 4w has the lowest p95 and highest RPS, 1w has the highest p95 and lowest RPS, 2w sits between them. This pattern has held across all 5 test runs without exception (excluding Run 1's connection pool anomaly).

---

### 5.3 spike_test.js

**Purpose:** Test system behavior under a sudden, instantaneous traffic burst. The key question: does the API absorb the spike without errors, and does performance return to normal afterward?

**Load profile:**
```
30s ramp 0→10 VUs   (baseline)
1m  hold at 10 VUs  (stable baseline)
10s ramp 10→300 VUs (SPIKE UP — abrupt)
30s hold at 300 VUs (spike sustained)
10s ramp 300→10 VUs (SPIKE DOWN — abrupt)
1m  hold at 10 VUs  (recovery observation)
10s ramp 10→0 VUs
```

**Think time:** `sleep(0.5)` — fixed.

**Thresholds:**
| Threshold | Value | Reasoning |
|-----------|-------|-----------|
| `p(95)<2000ms` | Generous | Spikes cause request queuing |
| `http_req_failed<15%` | 15% | Some errors acceptable at peak |
| `checks>85%` | 85% | Degraded but alive |

**What to watch:** The 10s ramp-up is intentionally abrupt (10→300 VUs in 10 seconds). This is the "surprise" traffic scenario. Systems with more workers absorb the burst faster because more event loop slots are available immediately.

**Variance note:** This test is the most sensitive to Docker CPU scheduling. The 10-second ramp phase can be disrupted by the WSL2 hypervisor yielding CPU at the wrong moment. Spike results vary more than stress results across runs.

---

### 5.4 soak_test.js

**Purpose:** Detect slow degradation over time — memory leaks, connection pool exhaustion, or database bloat that only manifests under sustained load. This test does not stress the system; it watches for drift.

**Load profile:**
```
1m  ramp 0→30 VUs
30m hold at 30 VUs  (sustained moderate load)
1m  ramp 30→0 VUs
```

**Think time:** `randomSleep(0.5, 2.0)` — realistic pacing.

**Thresholds:**
| Threshold | Value |
|-----------|-------|
| `p(95)<700ms` | Moderate — 30 VUs should be comfortable |
| `http_req_failed<1%` | Near-zero |
| `checks>95%` | Strong correctness |

**What to watch:**
- **Flat latency curve over 30 minutes** = system is stable, no leaks
- **Rising latency over time** = memory leak or connection exhaustion
- **Error rate climbing** = resource exhaustion (connection pool depleted)

**Expected result:** All configs produce identical results. 30 VUs is well below saturation for any config. The test proves endurance and stability, not scaling.

---

### 5.5 breakpoint_test.js

**Purpose:** Find the absolute maximum throughput the system can sustain before collapse. Unlike all other Phase B tests, this uses a **ramping-arrival-rate** executor — K6 controls RPS directly rather than VU count.

**Load profile:**
```
5m ramp 10→50 RPS   (warm up)
5m ramp 50→150 RPS  (push)
5m ramp 150→300 RPS (heavy)
5m ramp 300→500 RPS (extreme)
```

**Executor parameters:**
```js
executor: "ramping-arrival-rate"
startRate: 10          // iterations per second at start
preAllocatedVUs: 50    // VUs ready before test begins
maxVUs: 500            // K6 will spawn up to 500 VUs as needed
```

**Think time:** None — `// No sleep — arrival rate controls pacing`. In open-model executors, VUs do not sleep; K6 manages pacing by rate.

**Thresholds:**
```js
// Intentionally observational — we WANT to see where it breaks
http_req_duration: [{ threshold: "p(95)<5000", abortOnFail: true }]
checks: ["rate>0.80"]
```

The `abortOnFail: true` flag stops the test automatically if p95 exceeds 5 seconds — the system has collapsed beyond any useful measurement.

**Why arrival-rate matters:** In closed-model tests (constant-vus), if the server slows down, VUs wait longer between requests and effective RPS drops. This can mask collapse. In open-model (ramping-arrival-rate), K6 keeps sending at the target RPS regardless — if the server can't keep up, requests queue and eventually drop. This reveals the true ceiling.

**Expected result:** 4w sustains ~189 RPS indefinitely (all 5 runs). 1w collapses at ~60 RPS. 2w sits between them but varies: sometimes reaches ~189 RPS (when scheduling is favorable), sometimes degrades earlier. The 4w ceiling of 189 RPS is the most stable single data point in the entire dataset.

---

## 6. Phase C — Behavioral Tests

Phase C tests do not use `trafficMix()` (except recovery). They test specific system behaviors that are not visible in throughput-focused Phase B tests.

### 6.1 contention_test.js

**Purpose:** Test PostgreSQL row-level locking (`SELECT ... FOR UPDATE`) under high contention. Instead of spreading requests across 100 events, all 50 VUs target the **same event** simultaneously, forcing every booking request to compete for the same row lock.

**Load profile:** 50 VUs, 2 minutes. Fixed duration.

**What makes this test different:**
- Does not import `trafficMix()` — has its own traffic pattern
- Every iteration: one booking attempt + one event read (same event)
- `TARGET_EVENT_ID` configurable via `-e TARGET_EVENT_ID=1` (defaults to event 1)
- `setup()` checks the target event exists and warns if tickets are already exhausted

**Custom metrics:**
| Metric | Tracks |
|--------|--------|
| `contention_booking_success` | HTTP 200 booking creations |
| `contention_booking_sold_out` | HTTP 409 (ticket exhausted) |
| `contention_booking_latency` | Duration of each booking request specifically (Trend) |

The `contention_booking_latency` Trend is separate from `http_req_duration` — it isolates booking latency from the event read requests in the same iteration.

**Thresholds:**
| Threshold | Value |
|-----------|-------|
| `contention_booking_latency p(95)<3000ms` | Row locks should resolve quickly |
| `http_req_failed<5%` | No unexpected errors |
| `checks>95%` | All responses must be 200 or 409 |

**The 283-booking invariant:** Because event 1 is seeded with exactly 283 tickets, `contention_booking_success` always equals 283 across all runs and all configs (1w, 2w, 4w). This is the correctness proof — PostgreSQL's `FOR UPDATE` serializes concurrent writes correctly regardless of worker count. This invariant has held across all 5 runs without exception.

---

### 6.2 read_vs_write_test.js

**Purpose:** Compare system behavior under read-heavy vs write-heavy traffic to understand how write-path row locking affects overall throughput.

**Load profile:** Two sequential scenarios, 30 VUs each, 3 minutes each. Total ~7 minutes.

**Scenarios:**

| Scenario | startTime | Read % | Write % | Endpoints |
|----------|-----------|--------|---------|-----------|
| `read_heavy` | 0s | 90% | 10% | browse, view, search, list users, global stats (reads) + booking (write) |
| `write_heavy` | 190s | 40% | 60% | browse, view event (reads) + create booking 35%, cancel booking 25% (writes) |

The 190s start time for `write_heavy` ensures it begins after `read_heavy` finishes (60s + 30s gracefulStop + 100s buffer).

**Per-scenario thresholds:**
| Scenario | p(95) threshold |
|----------|----------------|
| `read_heavy` | 500ms |
| `write_heavy` | 1500ms |

Write-heavy is allowed more latency because booking creation acquires a row lock on the event and waits if another transaction holds it.

**Custom metrics:**
| Metric | Tracks |
|--------|--------|
| `read_heavy_bookings` | Successful bookings in read-heavy scenario |
| `write_heavy_bookings` | Successful bookings in write-heavy scenario |

**Expected result:** Both scenarios pass with 0% errors at moderate load (30 VUs). Write-heavy has slightly higher latency. The booking counts differ significantly: write-heavy produces ~3× more bookings per unit time because booking attempts are 35% of traffic vs 10%.

---

### 6.3 recovery_test.js

**Purpose:** Measure how quickly the system returns to normal latency after a traffic spike ends. Unlike `spike_test.js` (which focuses on behavior during the spike), this test has a long 4-minute post-spike observation window to measure the recovery curve.

**Load profile:**
```
1m  30 VUs  — baseline (establish normal p95)
10s 300 VUs — SPIKE UP
30s 300 VUs — sustained overload
10s 30 VUs  — SPIKE DOWN
4m  30 VUs  — recovery observation (long window)
20s 0 VUs   — ramp down
```

**Think time:** `sleep(0.5)` — fixed.

**Uses:** `trafficMix()` — same traffic distribution as other Phase B tests.

**Thresholds:**
| Threshold | Value | Reasoning |
|-----------|-------|-----------|
| `p(95)<10000ms` | Very generous | We want to observe recovery, not abort it |
| `http_req_failed<30%` | 30% | Spike will cause errors — don't abort |
| `checks>70%` | 70% | Minimal bar during spike phase |

These thresholds are intentionally loose. The test is observational — the metric of interest is not whether it passes, but what the recovery shape looks like in Grafana: how many seconds after the spike ends does p95 return to the baseline level established in the first minute.

**Key thesis metric:** Recovery time per worker config. More workers = faster recovery because queued requests drain faster when more event loop slots are available.

**Expected result across configs:** 4w recovers fastest, 1w slowest. Run 5 produced the clearest ordering: 4w (142ms) < 2w (448ms) < 1w (851ms), all 0% errors. This test has higher variance than the stress test because the 10s spike transitions are sensitive to Docker CPU scheduling timing.

---

## 7. How Tests Share Code

The import graph for the test suite:

```
helpers.js
    ↑ (imported by all files)
    
realistic_test.js
    ↑ (trafficMix imported by:)
    ├── load_test.js
    ├── stress_test.js
    ├── spike_test.js
    ├── soak_test.js
    ├── breakpoint_test.js
    └── recovery_test.js

standalone (no trafficMix):
    ├── baseline_test.js
    ├── endpoint_benchmark_test.js
    ├── contention_test.js
    └── read_vs_write_test.js
```

Tests that import `trafficMix` also re-export the booking counters:
```js
export { bookingSuccess, bookingFail, bookingSoldOut };
```
This makes the counters appear in the result JSON of every test that uses the traffic mix, allowing booking volume to be compared across test types and configs.

---

## 8. K6 Executors Used

| Executor | Tests | Description |
|----------|-------|-------------|
| `shared-iterations` (implicit) | realistic_test.js, baseline_test.js, load_test.js, stress_test.js, spike_test.js, soak_test.js, contention_test.js, recovery_test.js | VUs share a fixed duration. K6 manages concurrency via stages (ramping-vus) or fixed vus. |
| `constant-vus` (explicit) | endpoint_benchmark_test.js, read_vs_write_test.js | Fixed VU count for a fixed duration within named scenarios. |
| `ramping-arrival-rate` (explicit) | breakpoint_test.js | K6 controls iterations per second (RPS), not VU count. VUs are allocated dynamically up to `maxVUs`. |

The distinction between closed-model (vus-based) and open-model (arrival-rate) executors is critical to understanding why breakpoint results differ structurally from stress results. In closed model, slow responses reduce effective RPS. In open model, they do not — load keeps arriving regardless.

---

## 9. Thresholds and Pass/Fail Logic

K6 thresholds determine whether a test passes or fails. Each test has different thresholds calibrated to its purpose:

| Test | p(95) | Error rate | Checks | Reasoning |
|------|-------|-----------|--------|-----------|
| baseline | <300ms | <1% | >99% | Strict — idle system at 10 VUs |
| realistic | <500ms | <1% | >95% | Comfortable — 20 VUs with think time |
| endpoint_benchmark | per-scenario | <5% | >95% | Scenario-specific SLAs |
| load | <500ms | <1% | >95% | Normal operating SLA |
| stress | <1500ms | <10% | >90% | Relaxed — we expect degradation |
| spike | <2000ms | <15% | >85% | Burst tolerance |
| soak | <700ms | <1% | >95% | Stability: no drift over 30min |
| breakpoint | <5000ms (abort) | — | >80% | Observational — just don't crash K6 |
| contention | booking p95<3000ms | <5% | >95% | Lock waits should resolve |
| read_vs_write | read<500ms, write<1500ms | <5% | >95% | Per-scenario SLAs |
| recovery | <10000ms | <30% | >70% | Observational — observe recovery |

---

## 10. Output Files and Result Structure

Every test calls `saveSummary(data, testName)` in its `handleSummary` hook. This writes:

1. **Terminal output** — formatted K6 summary with colors
2. **JSON file** — `results/{WORKERS}/{testName}.json`

The JSON file contains the complete K6 summary data object:
- `metrics` — all built-in and custom metrics with their statistical values (avg, min, med, max, p90, p95)
- `root_group.checks` — all check pass/fail counts
- `state` — test run duration
- `options` — which percentiles were computed
- `setup_data` — data returned by `setup()` (e.g., contention test's `initialTickets`)

Result folders per worker config:
```
results/
├── 1w/   — all 10 test JSONs for 1-worker config
├── 2w/   — all 10 test JSONs for 2-worker config
└── 4w/   — all 10 test JSONs for 4-worker config
```

---

## 11. How to Run Tests

### Single test, single worker config

```bash
k6 run \
  -e WORKERS=4w \
  -e BASE_URL=http://localhost:8000 \
  --out experimental-prometheus-rw \
  -e K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write \
  tests/stress_test.js
```

### Override target event for contention test

```bash
k6 run -e WORKERS=1w -e TARGET_EVENT_ID=5 tests/contention_test.js
```

### Recommended run order (one full config)

Run in this sequence to avoid state issues (e.g., event tickets depleted before contention test):

1. `baseline_test.js` — verify health first
2. `endpoint_benchmark_test.js`
3. `load_test.js`
4. `stress_test.js`
5. `spike_test.js`
6. `soak_test.js`
7. `breakpoint_test.js`
8. Re-seed database: `docker compose exec api python seed_data.py --reset`
9. `contention_test.js` — needs fresh tickets
10. `read_vs_write_test.js`
11. `recovery_test.js`

Re-seeding before the contention test is important because thousands of booking requests during Phase B tests drain ticket availability across events.

### Re-seeding the database

```bash
docker compose exec api python seed_data.py --reset
```

This resets the database to its initial state: 1000 users, 100 events (each with 283 tickets), ~500 initial bookings.
