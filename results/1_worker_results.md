# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** 2026-03-29
**Configuration:** Docker (FastAPI + PostgreSQL), 1 Uvicorn worker
**Seed data:** 1,000 users, 100 events, 2,000 bookings (re-seeded before each test)
**Monitoring:** K6 → Prometheus remote write → Grafana dashboard (live visualization)
**Machine:** Windows 11, 16 GiB RAM
**K6 output:** `--out experimental-prometheus-rw` with trend stats: p(50), p(90), p(95), p(99), avg, min, max

---

## Summary Table

| Test | Type | VUs | Duration | p(95) | Median | Avg | Error Rate | RPS | Status |
|------|------|-----|----------|-------|--------|-----|------------|-----|--------|
| Baseline | Smoke | 10 | 30s | 72ms | — | 24ms | 0% | 90 | PASS |
| Endpoint Benchmark | Isolation | 20 | 5x1min | 78–196ms | — | 35–98ms | 0% | 86 | PASS |
| Load | Normal load | 50 | 8min | 56ms | 21ms | 25ms | 0% | 40 | PASS |
| Stress | Overload | 300 | 8min | 510ms | 181ms | 1.08s | 1.43% | 84 | PASS |
| Spike | Burst | 300 | 3.5min | 60s | 29ms | 6.13s | 9.91% | 12 | FAIL |
| Soak | Endurance | 30 | 32min | 43ms | 18ms | 37ms* | 0% | 10 | PASS |
| Breakpoint | Capacity | 500 | 15min | 30.3s | 31ms | 3.06s | 4.92% | 150 peak | ABORT |
| Contention | Locking | 50 | 2min | 156ms | 40ms | 120ms | 0% | 134 | PASS |
| Read vs Write (read) | Traffic profile | 30 | 3min | 121ms | 30ms | 74ms | 0% | ~51 | PASS |
| Read vs Write (write) | Traffic profile | 30 | 3min | 159ms | 41ms | 58ms | 0% | ~51 | PASS |

*Soak avg inflated by one 19m30s outlier (likely leftover connection from prior test). Successful responses avg = 37ms.

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Purpose:** Verify all endpoints are functional before heavy testing. Acts as a sanity check — if this fails, no point running further tests.

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 72ms |
| Avg response time | 24ms |
| Error rate | 0% |
| Checks passed | 100% |
| Total requests | ~2,700 |
| RPS | ~90 |

**Grafana observations:**
- Active VUs panel showed a flat line at 10 VUs for the 30s duration.
- Response Time Percentiles showed all four lines (p50, p90, p95, p99) clustered between 20–80ms — very tight spread indicating consistent performance.
- Error Rate panel showed a flat 0% line.
- RPS panel showed steady ~90 req/s.

**Conclusion:** All endpoints healthy and responsive. The system handles 10 concurrent users with sub-100ms latency across all percentiles. This establishes a reference point for comparing all subsequent tests.

---

### A.2 Endpoint Benchmark

**Purpose:** Isolate each endpoint category under controlled load to understand per-endpoint performance characteristics. Each scenario runs sequentially (via `startTime` offset) so they don't interfere with each other.

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario, 10s gap between scenarios. Total duration: ~5 min 40s.

**Results:**

| Scenario | Endpoints | p(95) | Avg | Threshold | Margin |
|----------|-----------|-------|-----|-----------|--------|
| Light Reads | GET /health, /users/{id}, /events/{id}, /bookings/{id} | 100ms | 40ms | <200ms | 2x |
| List Reads | GET /users/, /events/, /bookings/ (limit=100) | 196ms | 98ms | <500ms | 2.5x |
| Search & Filter | GET /events/search, /events/upcoming, /users/{id}/bookings, /events/{id}/bookings | 84ms | 40ms | <500ms | 6x |
| Writes | POST /bookings/, PATCH /bookings/{id}/cancel | 110ms | 48ms | <1000ms | 9x |
| Heavy Aggregations | GET /events/{id}/stats, /events/popular, /stats | 78ms | 35ms | <1500ms | 19x |

- **Total requests:** 29,182
- **Checks passed:** 100% (29,182/29,182)
- **Error rate:** 0%
- **Total RPS:** ~86

**Grafana observations:**
- Active VUs panel showed a distinct step pattern — 20 VUs appearing for each scenario window, with brief drops to 0 between scenarios. This visually confirms scenarios ran sequentially without overlap.
- RPS by Endpoint panel showed each endpoint group dominating during its time window, with clear handoffs between scenarios.
- Response Time by Endpoint (p95) showed all endpoints clustered between 50–200ms with stable horizontal lines — no degradation within any scenario.
- CPU Usage remained at ~5-10% throughout, indicating the system was barely utilized at 20 VUs.

**Analysis:**

1. **List Reads are the slowest** (196ms p95). This is expected — these endpoints serialize up to 100 records per response, including JSON encoding of nested objects. The bottleneck is serialization and data transfer, not query execution.

2. **Heavy Aggregations are surprisingly fast** (78ms p95). Despite involving JOINs, GROUP BY, and subqueries, the PostgreSQL indexes make these queries efficient. The global stats endpoint (which aggregates across all tables) benefits from the database's query optimizer.

3. **Writes are faster than List Reads** (110ms vs 196ms). The `with_for_update()` row locking adds minimal overhead at this concurrency level. Write operations touch only 1-2 rows, while list reads return up to 100.

4. **Search & Filter is fast** (84ms p95). The `location` column index makes filtered queries efficient even with the LIKE operator.

**Conclusion:** At 20 VUs, every endpoint has significant headroom before reaching its threshold. The performance hierarchy (PK lookups < aggregations < search < writes < list reads) provides a baseline for understanding how each endpoint contributes to overall system behavior under mixed traffic.

---

## Phase B — Standard Test Types (Mixed Realistic Traffic)

All Phase B tests use the same weighted traffic distribution to ensure comparable results:

| Weight | Operation | Endpoint |
|--------|-----------|----------|
| 25% | Browse events | GET /events/ |
| 15% | View event | GET /events/{id} |
| 10% | Search events | GET /events/search?location=... |
| 8% | Upcoming events | GET /events/upcoming |
| 10% | List users | GET /users/ |
| 5% | User bookings | GET /users/{id}/bookings |
| 12% | Create booking | POST /bookings/ |
| 5% | Cancel booking | PATCH /bookings/{id}/cancel |
| 5% | Event stats | GET /events/{id}/stats |
| 3% | Popular events | GET /events/popular |
| 2% | Global stats | GET /stats |

This distribution was chosen to simulate realistic user behavior: browsing dominates, followed by booking activity, with analytics endpoints accessed least frequently.

---

### B.1 Load Test

**Purpose:** Simulate normal-to-peak traffic and verify the system handles expected production load without degradation.

**Config:** Ramp 0 → 50 VUs (2 min) → hold 50 VUs (5 min) → ramp down to 0 (1 min). Total: ~8 min.
**Thresholds:** p(95) < 500ms, p(99) < 1000ms, error rate < 1%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 56ms |
| p(99) | ~80ms |
| Median | 21ms |
| Avg | 25ms |
| Max | 692ms |
| Error rate | 0% |
| Checks passed | 100% (19,059/19,059) |
| Total requests | 19,060 |
| RPS | ~40 |
| Bookings created | 2,280 |

**Grafana observations:**
- Active VUs showed a textbook ramp shape: smooth climb from 0 to 50, flat hold at 50, clean ramp down to 0.
- RPS panel showed steady ~40-50 req/s during the hold phase, with the ramp shape mirroring VU count.
- Response Time Percentiles remained flat throughout the entire test. p50 stayed at ~20ms, p95 at ~55ms, with no upward trend even as VUs increased to 50. This flat profile indicates the system is well within its capacity.
- Error Rate showed a constant 0% line.
- Response Time vs VUs (bottom panel) confirmed latency stayed flat as VUs increased — the orange p95 line remained horizontal at ~55ms while the blue VU line climbed to 50.
- RPS by Endpoint showed BrowseEvents dominating (~13 req/s) as expected from the 25% traffic weight.
- Booking Metrics panel showed 2,280 — the custom `booking_success` counter is working correctly with the realistic traffic profile.
- CPU Usage was ~5% — barely registering.

**Conclusion:** At normal production load (50 VUs), the system operates with massive headroom. Latencies are stable, error rate is zero, and CPU is barely utilized. The flat response time curve confirms there is no degradation as load increases within this range. This result establishes that 50 VUs / 40 RPS is comfortably within the single worker's capacity.

---

### B.2 Stress Test

**Purpose:** Progressive overload to find the degradation point. Unlike the load test (which stays within expected limits), the stress test intentionally pushes past capacity to observe how the system fails.

**Config:** Ramp 0 → 50 (1 min) → 50 → 100 (2 min) → 100 → 200 (2 min) → 200 → 300 (2 min) → 300 → 0 (1 min). Total: ~8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 510ms |
| Median | 181ms |
| Avg | 1.08s |
| Max | 60s (timeout) |
| Error rate | 1.43% (611 requests) |
| Checks passed | 98.56% (42,022/42,633) |
| Total requests | 42,634 |
| RPS | ~84 avg, peaked ~200 |
| Bookings | 5,129 success / 97 failed / 2 sold out |

**Grafana observations:**
- Active VUs showed the staircase ramp from 0 to 300 and back down.
- **RPS peaked at ~200 req/s around 200 VUs, then COLLAPSED.** This is the most critical observation — adding more VUs past 200 actually *decreased* throughput. The system became saturated and started queuing requests instead of processing them.
- Response Time Percentiles showed a dramatic hockey stick: flat near 0ms until ~200 VUs, then p99 jumped to **30 seconds** and p95 to several seconds. The p50 (median) remained relatively low, meaning most requests still completed quickly, but the tail latency exploded.
- Error Rate was 0% up to ~200 VUs, then **spiked to ~50% at 300 VUs**. The errors were connection timeouts (60s), not application errors.
- Response Time vs VUs showed the exact inflection point around 200 VUs where latency went exponential — the response time curve went vertical while VUs continued climbing linearly.
- CPU reached only ~18% at peak — confirming the bottleneck is NOT CPU but the single Uvicorn worker's async event loop and connection pool.

**Analysis:**

The stress test reveals the single worker's saturation curve. At 50-100 VUs, the system handles the load comfortably. At 100-200 VUs, latency increases but throughput continues to grow. Past 200 VUs, the system enters a cascade failure mode:

1. New requests arrive faster than the worker can process them
2. Requests queue up, increasing wait times
3. Some requests hit the 60s timeout, consuming a connection slot until timeout
4. This reduces available connections, making the problem worse
5. RPS drops because fewer requests complete

The fact that CPU stays low proves this is an I/O-bound bottleneck: the single Python event loop can only context-switch between so many concurrent connections before losing efficiency.

**Note:** After the test, the API remained functional but strained. Prometheus showed increased scrape times.

**Conclusion:** The single worker degrades gracefully under *gradual* overload (p95=510ms, error rate=1.43%), but the degradation curve is non-linear. The system has a practical ceiling around 200 VUs / 200 RPS, beyond which performance collapses.

---

### B.3 Spike Test

**Purpose:** Test system response to a sudden traffic burst and — critically — whether the system recovers after the spike subsides. This simulates scenarios like a flash sale, viral event, or DDoS attack.

**Config:** 0 → 10 VUs (30s) → hold 10 (1 min) → spike 10 → 300 (10s) → hold 300 (30s) → drop 300 → 10 (10s) → hold 10 (1 min) → 0. Total: ~3.5 min.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

**Note:** This test was run without restarting the API after the stress test, simulating a realistic scenario where a spike hits an already-loaded system.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | **60s (timeout)** |
| Median | 29ms |
| Avg | 6.13s |
| Max | 60s |
| Error rate | 9.91% (286 requests) |
| Checks passed | 90.08% (2,598/2,884) |
| Total requests | 2,885 |
| RPS | ~12 (severely degraded) |
| Bookings | 330 success / 28 failed / 1 sold out |

**Threshold result:** FAILED — p(95) crossed the 2000ms threshold.

**Grafana observations:**
- Active VUs showed the sharp spike: flat at 10, then a near-vertical jump to 300, hold for 30s, sharp drop back to 10.
- **THE CRITICAL FINDING: The system DID NOT RECOVER.** After VUs dropped from 300 back to 10 at ~14:37, the error rate **continued climbing from ~40% to 60%** and RPS stayed near zero. Even with only 10 VUs, the API was still struggling minutes after the spike ended.
- Response Time vs VUs (the most important chart for this test) showed p95 jumping to 30s during the spike — and then **staying at 30s after VUs dropped to 10**. The green p50 line also remained elevated. The system never recovered.
- RPS dropped to zero during and after the spike, with only brief flickers of activity.
- CPU dropped back to near 0% after the spike — the worker wasn't busy with computation. It was stuck processing a backlog of queued/timed-out connections.

**Comparison with Stress Test (same 300 VUs):**

| Metric | Stress (gradual ramp) | Spike (sudden burst) |
|--------|----------------------|---------------------|
| Time to reach 300 VUs | 7 minutes | 10 seconds |
| p(95) | 510ms | 60s (timeout) |
| Error rate | 1.43% | 9.91% |
| RPS at peak | ~200 | ~60 |
| Recovery | Graceful ramp-down | **No recovery** |
| Total requests | 42,634 | 2,885 |

**Analysis:**

The spike test exposes the single worker's most critical weakness: **inability to recover from sudden overload.** When load increases gradually (stress test), the event loop has time to process each wave of new connections. When 290 new connections arrive in 10 seconds, the event loop becomes saturated:

1. The 300 VU burst creates ~300 simultaneous connections
2. The worker tries to context-switch between all of them
3. None complete quickly, so all start accumulating wait time
4. After the spike drops to 10 VUs, the worker still has a backlog of timed-out or in-flight requests
5. New requests from the remaining 10 VUs get queued behind the backlog
6. The cycle doesn't break because the worker can't process the drain fast enough

This is fundamentally different from the stress test because there's no "ramp" for the system to adapt. The sudden nature of the spike overwhelms the single process's ability to manage connections.

**Conclusion:** This is the strongest argument for multi-worker deployment. A single worker cannot survive a sudden traffic spike and — more importantly — cannot self-recover after one. In production, this would require a manual restart or automatic health-check restart (which we have configured via Docker's `restart: unless-stopped`).

---

### B.4 Soak Test

**Purpose:** Long-running stability test to detect memory leaks, connection pool exhaustion, or gradual latency creep that only appears over extended periods. These are the types of issues that short tests (30s–8min) would miss.

**Config:** Ramp 0 → 30 VUs (1 min) → hold 30 VUs (30 min) → ramp down (1 min). Total: ~32 min.
**Thresholds:** p(95) < 700ms, error rate < 1%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 43ms |
| Median | 18ms |
| Avg (successful) | 37ms |
| Max | 19m 30s (single outlier) |
| Error rate | 0.00% (1 request out of 19,972) |
| Checks passed | 99.99% (19,970/19,971) |
| Total requests | 19,972 |
| RPS | ~10 |
| Bookings created | 2,372 |
| Duration | 32 min 1s |

**Note:** The avg of 96ms and max of 19m30s are inflated by a single outlier — likely a lingering connection from the previous test session. When looking at successful response metrics only: avg = 37ms, p(95) = 43ms.

**Grafana observations:**
- Active VUs showed a flat line at 30 VUs for the entire 30-minute hold period.
- **Response Time Percentiles stayed absolutely flat for 30 minutes.** p50 at ~20ms, p90 at ~30ms, p95 at ~43ms. No upward trend whatsoever. This flat line is the most important observation — it proves there are no gradual resource leaks.
- RPS held steady at ~20-30 req/s throughout, with normal minor fluctuations.
- Error Rate showed 0% for the entire duration.
- CPU Usage stayed flat at ~5%, with one brief spike to ~70% around minute 25 (likely an OS background process, not the API).
- Memory Usage showed a completely flat green line — no growth over 30 minutes. This rules out memory leaks in the application.
- Response Time vs VUs showed both p50 and p95 as flat horizontal lines, with VUs constant at 30. Perfect stability.

**Analysis:**

The soak test answers three critical questions:

1. **Memory leaks?** No. Memory usage was flat for 32 minutes. The FastAPI application, SQLAlchemy ORM, and PostgreSQL connection pool all handle long-running operation without accumulating leaked objects.

2. **Connection pool exhaustion?** No. With `pool_size=5` and `max_overflow=10` (15 total connections), the pool handled 30 VUs continuously for 30 minutes without running out of connections. This validates that connections are properly returned to the pool after each request.

3. **Latency creep?** No. p(95) stayed at 43ms from minute 1 to minute 32. Some systems show gradual latency increase due to table bloat, index fragmentation, or GC pressure — none of these are present here.

**Conclusion:** The single-worker API is rock solid under sustained moderate load. Its weakness is burst capacity (spike/stress), not endurance. For applications with predictable, steady traffic patterns, a single worker is perfectly adequate.

---

### B.5 Breakpoint Test

**Purpose:** Find the absolute maximum throughput using open-model load. Unlike closed-model tests (load, stress, spike) where VUs wait for responses before sending new requests, the open-model sends requests at a target rate regardless of response times. This is more representative of real-world traffic where users don't wait for each other.

**Config:** ramping-arrival-rate executor. Ramp from 10 to 500 iterations/s over 20 minutes. preAllocatedVUs = 50, maxVUs = 500. Auto-abort when p(95) > 5000ms.
**Thresholds:** p(95) < 5000ms with abortOnFail (the purpose is to find where it breaks, not to pass).

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 30.3s |
| Median | 31ms |
| Avg | 3.06s |
| Max | 60s (timeout) |
| Error rate | 4.92% (2,131 requests) |
| Total requests | 43,313 |
| Peak actual RPS | **~150 req/s** |
| VUs at abort | 500 (maxVUs exhausted) |
| Dropped iterations | 67,560 |
| Bookings | 5,065 success / 246 failed / 10 sold out |
| Duration | 15 min 16s (aborted at ~75% of 20 min) |
| Target rate at abort | ~310 iters/s |

**Grafana observations:**
- Active VUs showed a smooth ramp from 0 to 500, but unlike closed-model tests, VUs are allocated by K6 to meet the target rate. The ramp steepened dramatically once the system became saturated (more VUs needed to attempt the target rate when responses were slow).
- **RPS peaked at ~150 req/s around 15:36, then collapsed.** The system sustained ~150 RPS for several minutes before the cascade began. This is the true throughput ceiling.
- Response Time Percentiles showed a staircase pattern: flat near 0ms for the first 7 minutes, then a series of jumps — first to ~5s, then 10s, 20s, 30s, and finally 60s (timeout). Each jump represents a new wave of requests that can't be processed in time.
- Error Rate climbed from 0% to ~40%, then ~80%, then ~95% in the final minutes before abort. The error rate acceleration mirrors the latency staircase.
- Response Time vs VUs showed p50 and p95 both rising exponentially once VUs exceeded ~200, while VUs continued climbing linearly to 500.
- CPU reached only ~20% — again confirming this is not a CPU bottleneck.
- Dropped iterations (67,560) means K6 wanted to send ~67,000 more requests but couldn't allocate enough VUs to keep up with the target rate. This shows how far beyond capacity the target was.

**Analysis:**

The breakpoint test identifies the single worker's hard ceiling under realistic (open-model) conditions:

1. **Sustainable throughput: ~150 RPS.** The system maintained this rate with low latency for several minutes before degradation began.
2. **Breakpoint trigger: ~200-250 target iters/s.** When the target rate exceeded what the system could actually deliver, requests began queuing.
3. **Collapse is rapid.** Once saturation begins, the cascade from "working" to "completely overwhelmed" takes only 2-3 minutes. There is no graceful degradation plateau — the system falls off a cliff.
4. **VU exhaustion.** K6 allocated all 500 maxVUs trying to meet the target rate, meaning the system couldn't handle requests fast enough and connections accumulated.

**Closed vs Open Model Comparison:**

| Model | Test | Max sustained RPS | Peak VUs | Error rate |
|-------|------|-------------------|----------|------------|
| Closed | Stress test | ~200 RPS | 300 | 1.43% |
| Open | Breakpoint test | ~150 RPS | 500 | 4.92% |

The closed model achieves higher RPS because VUs self-regulate: when responses slow down, VUs send fewer requests. The open model keeps pushing regardless, which is why it finds a lower but more realistic ceiling.

**Conclusion:** The single worker's absolute capacity is **~150 RPS** under open-model load. Beyond this, the system enters rapid cascade failure. This number becomes the key comparison metric for the 4-worker test.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Purpose:** Test PostgreSQL row-level locking (`SELECT ... FOR UPDATE` via SQLAlchemy's `with_for_update()`) under extreme contention. All 50 VUs simultaneously try to book the *same event* (event_id=1), creating maximum lock contention on a single database row.

**Config:** 50 VUs, 2 min duration. Each iteration: attempt to book event_id=1, then read event_id=1's details. Custom metric `contention_booking_latency` tracks booking-specific response times.
**Thresholds:** booking latency p(95) < 3000ms, error rate < 5%.

**Results:**

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 187ms |
| HTTP p(95) | 156ms |
| Avg | 120ms |
| Median | 40ms |
| Max | 20.6s |
| Error rate | 0.00% |
| Checks passed | 100% (16,208/16,208) |
| Total requests | 16,209 |
| RPS | ~134 |
| Bookings success | 283 |
| Sold out (409) | 7,821 |

**Grafana observations:**
- Active VUs showed a flat line at 50 VUs for 2 minutes.
- **CPU spiked to 75% at test start** — this is the initial burst when all 50 VUs hit event_id=1 simultaneously and tickets are still available. Each booking requires: row lock acquisition → capacity check → booking insert → capacity decrement → commit. With 50 concurrent requests on the same row, PostgreSQL serializes these operations via the lock queue. Once tickets sold out (~10-15 seconds in), CPU dropped to ~15% because 409 "sold out" responses are cheap (no lock needed — just a capacity check that returns immediately).
- RPS by Endpoint showed ContentionBooking (~70-80 req/s) and ContentionEventRead (~70-80 req/s) running in parallel, as expected (each iteration does both operations).
- Response Time by Endpoint (p95) showed ContentionBooking at ~800ms while ContentionEventRead was much lower (~100ms). The reads don't need row locks, so they complete faster.
- Booking Metrics panels showed "No data" — this is expected because the contention test uses its own custom counters (`contention_booking_success`, `contention_booking_sold_out`) rather than the `booking_success` counter from the realistic traffic profile.
- Response Time vs VUs showed p95 at ~250ms and p50 at ~100ms, both flat — no degradation over the 2-minute window.

**Analysis:**

The contention test validates the correctness and performance of the pessimistic locking strategy:

1. **Correctness:** Exactly 283 bookings succeeded (matching the event's ticket capacity). Every subsequent attempt correctly received a 409 "sold out" response. No double-bookings, no overselling, no deadlocks.

2. **Lock fairness:** PostgreSQL's lock queue processes requests in FIFO order. With 50 VUs, each booking request waits in the lock queue for ~50-100ms (average). This is fast because each critical section (check capacity → insert → decrement) is very short.

3. **Performance under contention:** Even with 50 VUs fighting over a single row, p(95) stayed at 187ms for bookings. Compare this to the stress test where 300 VUs on *different* events produced p(95)=510ms — the lock contention on a single row adds less latency than general connection saturation.

4. **Two-phase behavior:** The test has a natural transition — Phase 1 (tickets available, ~15s) involves heavy locking with actual writes, Phase 2 (sold out, ~105s) involves lightweight capacity checks returning 409. This is visible in the CPU spike pattern.

**Conclusion:** The `with_for_update()` pessimistic locking strategy is highly effective for preventing booking race conditions. It maintains correctness under extreme contention (50 concurrent users, single event) with zero deadlocks and sub-200ms latency. The locking overhead is modest and predictable.

---

### C.2 Read vs Write Test

**Purpose:** Compare system behavior under read-heavy vs write-heavy traffic to quantify how write operations (with their row locks and transaction overhead) affect overall system performance.

**Config:** Two sequential scenarios at 30 VUs, 3 min each, with a 10s gap:

| Scenario | Profile | Operations |
|----------|---------|------------|
| `read_heavy` | 90% reads / 10% writes | Browse events (30%), view event (20%), search (15%), list users (15%), global stats (10%), create booking (10%) |
| `write_heavy` | 40% reads / 60% writes | Browse events (20%), view event (20%), create booking (35%), cancel booking (25%) |

**Thresholds:** read_heavy p(95) < 500ms, write_heavy p(95) < 1500ms, error rate < 5%.

**Results:**

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 121ms | 159ms |
| Median | 30ms | 41ms |
| Avg | 74ms | 58ms |
| Max | 10.32s | 301ms |
| Error rate | 0% | 0% |
| Bookings created | 964 | — |

- **Total requests:** 19,070
- **Checks passed:** 100% (19,069/19,069)
- **Combined RPS:** ~51

**Grafana observations:**
- Active VUs showed two distinct 30-VU blocks — read_heavy first, then a brief dip to 0, then write_heavy. Both maintained a flat 30 VUs for their 3-minute duration.
- RPS panel showed consistent ~50-55 req/s during both scenarios, with a brief dip during the gap between them. Interestingly, write-heavy achieved similar RPS to read-heavy despite more expensive operations.
- Response Time Percentiles showed p99 at ~1s initially (read-heavy phase), then settling to ~150-200ms in both phases. The initial spike in read-heavy was likely a warmup artifact.
- Response Time by Endpoint (p95) showed all endpoints clustered between 100-200ms, with WH_CancelBooking slightly higher. No dramatic differences between read and write endpoints.
- Error Rate showed 0% throughout both scenarios.
- Response Time vs VUs showed both p50 (~30-40ms) and p95 (~130-150ms) as flat horizontal lines, with VUs constant at 30. No degradation over time in either scenario.
- CPU at ~5-10% for both scenarios — minimal system utilization.
- Booking Metrics panels showed "No data" — this test uses its own custom counters (`read_heavy_bookings`, `write_heavy_bookings`).

**Analysis:**

| Metric | Read-heavy | Write-heavy | Ratio (W/R) |
|--------|-----------|-------------|-------------|
| p(95) | 121ms | 159ms | 1.31x |
| Median | 30ms | 41ms | 1.37x |

1. **Write-heavy p95 is 1.3x slower.** Write operations need row locks (`SELECT ... FOR UPDATE`), transaction commits, and capacity validation. Reads are simple SELECT queries that don't acquire exclusive locks.

2. **Write-heavy average is paradoxically lower** (58ms vs 74ms). The read-heavy scenario had one 10.32s outlier that pulled the average up. Looking at medians gives a cleaner comparison: 41ms vs 30ms (1.37x ratio).

3. **Both profiles are clean at 30 VUs.** Zero errors, stable latency, consistent RPS. The 1.3x penalty for write-heavy traffic is modest.

4. **The gap would likely widen at higher concurrency.** At 30 VUs, lock contention is minimal because writes are spread across 100 events. At 200+ VUs (like the stress test), write locks would queue more frequently, amplifying the read/write performance gap.

**Conclusion:** Write-heavy traffic adds ~30% latency at p95 compared to read-heavy traffic at moderate load (30 VUs). The performance impact is measurable but modest, validating the pessimistic locking approach as a reasonable tradeoff between correctness and performance.

---

## System Behavior Under Failure

### Observed Failure Patterns

| Test | Peak VUs | API Status After | Recovery |
|------|----------|-----------------|----------|
| Load (50 VUs) | 50 | Healthy | Self-recovered |
| Stress (300 VUs gradual) | 300 | Strained but responsive | Self-recovered |
| Spike (300 VUs sudden) | 300 | Unresponsive | Required restart |
| Breakpoint (500 VUs) | 500 | Crashed | Required restart |
| Soak (30 VUs, 32 min) | 30 | Healthy | N/A |

### Root Cause Analysis

The single Uvicorn worker runs one Python asyncio event loop. When concurrent connections exceed what the loop can process:

1. **Connection queue builds up** — each connection holds a slot even while waiting
2. **Event loop starvation** — the loop spends more time context-switching than doing work
3. **Timeout cascade** — slow requests hit the 60s timeout, but the connection isn't freed until then
4. **Self-reinforcing failure** — fewer available connections → new requests wait longer → more timeouts → even fewer connections

This is NOT a CPU bottleneck (CPU never exceeded 20% except the contention test's initial burst). It is a concurrency bottleneck inherent to single-process Python applications.

### Important Context for the Thesis

The bottleneck being the event loop (not CPU) means:
- **Vertical scaling (faster CPU) won't help.** The CPU is idle.
- **Horizontal scaling (more workers) should help significantly.** Each worker gets its own event loop, multiplying the concurrent connection capacity.
- This motivates the 4-worker comparison — we expect the ceiling to increase from ~150 RPS to potentially ~400-600 RPS.

---

## Key Conclusions — 1 Uvicorn Worker

### Performance Envelope

| Metric | Value | Context |
|--------|-------|---------|
| Comfortable capacity | 50 VUs / 40 RPS | p(95) < 60ms, 0% errors |
| Maximum throughput | ~150 RPS | Open-model breakpoint ceiling |
| Degradation point | 200+ VUs | Latency goes exponential, errors begin |
| Collapse point | 300 VUs sudden | System becomes unresponsive, no recovery |

### Architectural Strengths
1. **Excellent low-load performance:** Sub-60ms p(95) at 50 VUs
2. **Perfect stability:** 32-minute soak test with zero degradation
3. **Correct concurrency control:** `with_for_update()` prevents double-booking with zero deadlocks
4. **No resource leaks:** Flat memory and latency curves over time

### Architectural Weaknesses
1. **Single event loop bottleneck:** Limits concurrent connection handling regardless of CPU availability
2. **No spike recovery:** Sudden traffic bursts overwhelm the worker permanently
3. **Non-linear degradation:** Performance doesn't degrade proportionally — it collapses rapidly past the saturation point

### Implications for 4-Worker Comparison
The 4-worker configuration should address the primary bottleneck (single event loop) by running 4 independent Python processes. Expected improvements:
- Higher throughput ceiling (potentially 4x at ~600 RPS)
- Better spike resilience (load distributed across workers)
- Faster recovery after overload (individual workers may survive even if some become saturated)
- Similar per-request latency at low load (the bottleneck only matters under high concurrency)
