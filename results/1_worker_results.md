# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** 2026-03-31
**Configuration:** Docker (FastAPI + PostgreSQL), 1 Uvicorn worker
**Seed data:** 1,000 users, 100 events, 2,000 bookings (re-seeded before each test via `run_tests.sh`)
**Monitoring:** K6 → Prometheus remote write → Grafana dashboard (live visualization)
**Machine:** Windows 11, 32 GiB RAM
**K6 output:** `--out experimental-prometheus-rw` with trend stats: p(50), p(90), p(95), p(99), avg, min, max
**Test runner:** Automated via `run_tests.sh` (re-seed → run → restart if crashed → 30s cool-down)
**Resource limits:** API 2 CPU / 1 GB, PostgreSQL 2 CPU / 1 GB, Prometheus 1 CPU / 512 MB

---

## Summary Table

| Test | Type | VUs | Duration | p(95) | Median | Avg | Error Rate | RPS | Status |
|------|------|-----|----------|-------|--------|-----|------------|-----|--------|
| Baseline | Smoke | 10 | 32s | 62ms | 22ms | 28ms | 0% | 85 | PASS |
| Endpoint Benchmark | Isolation | 20 | ~12.6min | 42–107ms* | — | 91ms | 0.10% | 25 | PARTIAL FAIL |
| Load | Normal load | 50 | 8min | 34ms | 16ms | 38ms | 0% | 32 | PASS |
| Stress | Overload | 300 | ~26min | 353ms | 163ms | 601ms | 0.54% | 29 | PASS |
| Spike | Burst | 300 | 4min | 60s | 27ms | 5.76s | 9.03% | 12 | FAIL |
| Soak | Endurance | 30 | 32min | 28ms | 13ms | 16ms | 0% | 7 | PASS |
| Breakpoint | Capacity | 500 | ~17.5min | 19.3s | 21ms | 2.97s | 9.11% | 39 | ABORT |
| Contention | Locking | 50 | 2min | 40ms | 14ms | 18ms | 0% | 144 | PASS |
| Read vs Write (read) | Traffic profile | 30 | 3min | 38ms | — | 22ms | 0% | ~43 | PASS |
| Read vs Write (write) | Traffic profile | 30 | 3min | 56ms | — | 22ms | 0% | ~43 | PASS |

*Endpoint benchmark: light reads 42ms, list reads 107ms, search 43ms, writes 90ms. Heavy aggregations **failed** at 60,231ms (threshold <1500ms) due to scenario overlap — see analysis below.

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Purpose:** Verify all endpoints are functional before heavy testing. Acts as a sanity check — if this fails, no point running further tests.

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 62ms |
| p(90) | 51ms |
| Avg response time | 28ms |
| Median (p50) | 22ms |
| Max | 214ms |
| Error rate | 0% |
| Checks passed | 100% (3,686/3,686) |
| Total requests | 2,717 |
| RPS | ~85 |
| Iterations | 194 (6.06/s) |

**Grafana observations:**
- Active VUs panel showed a flat line at 10 VUs for the 30s duration.
- Response Time Percentiles showed all four lines (p50, p90, p95, p99) clustered between 20–65ms — very tight spread indicating consistent performance.
- Error Rate panel showed a flat 0% line.
- RPS panel showed steady ~85 req/s.

**Conclusion:** All endpoints healthy and responsive. The system handles 10 concurrent users with sub-65ms latency across all percentiles. This establishes a reference point for comparing all subsequent tests.

---

### A.2 Endpoint Benchmark

**Purpose:** Isolate each endpoint category under controlled load to understand per-endpoint performance characteristics. Each scenario runs sequentially (via `startTime` offset) so they don't interfere with each other.

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario, 10s gap between scenarios. Total: ~12.6 min (extended due to graceful stop overlap — see analysis).

**Results:**

| Scenario | Endpoints | p(95) | Avg | Threshold | Result |
|----------|-----------|-------|-----|-----------|--------|
| Light Reads | GET /health, /users/{id}, /events/{id}, /bookings/{id} | 42ms | — | <200ms | PASS |
| List Reads | GET /users/, /events/, /bookings/ (limit=100) | 107ms | — | <500ms | PASS |
| Search & Filter | GET /events/search, /events/upcoming, /users/{id}/bookings, /events/{id}/bookings | 43ms | — | <500ms | PASS |
| Writes | POST /bookings/, PATCH /bookings/{id}/cancel | 90ms | — | <1000ms | PASS |
| Heavy Aggregations | GET /events/{id}/stats, /events/popular, /stats | 60,231ms | — | <1500ms | **FAIL** |

- **Total requests:** 18,842
- **Checks passed:** 99.90% (18,823/18,842)
- **Failed checks:** "popular 200" (4 fails), "global stats 200" (14 fails)
- **Error rate:** 0.10% (18 failures)
- **Max VUs observed:** 40 (due to scenario overlap)
- **Total RPS:** ~25 (averaged across 12.6 min including inter-scenario gaps)

**Analysis — Heavy Aggregation Failure:**

The heavy_aggregations failure at 60,231ms p(95) is caused by **scenario overlap during graceful stop**. Each scenario has a 30s `gracefulStop` period, but the inter-scenario gap is only 10s (startTime offsets of 70s with 60s duration). This means:

1. The writes scenario (startTime 210s) runs VUs from 210–270s, with graceful stop allowing VUs to linger until 300s
2. The heavy_aggregations scenario starts at 280s
3. During 280–300s, both writes VUs (draining) and heavy_aggregations VUs (starting) run simultaneously — hence 40 max VUs
4. Writes VUs hold row locks (INSERT/UPDATE with `SELECT ... FOR UPDATE`) while heavy aggregation queries attempt JOINs, GROUP BY, and subqueries on the same tables
5. The lock contention causes heavy aggregation queries to wait, with some timing out at 60s

The 18 failed checks (4 popular, 14 global stats) confirm that the most data-intensive endpoints — which scan across bookings + events tables — are the ones affected by write lock contention.

**Key insight for the thesis:** This demonstrates how write-heavy operations can degrade analytical query performance through lock contention, even at moderate concurrency (20 + 20 VUs). In a production system, separating read replicas from write traffic would mitigate this.

**Results excluding heavy_aggregations:**

| Scenario | p(95) | Threshold | Margin |
|----------|-------|-----------|--------|
| Light Reads | 42ms | <200ms | 4.8x |
| List Reads | 107ms | <500ms | 4.7x |
| Search & Filter | 43ms | <500ms | 11.6x |
| Writes | 90ms | <1000ms | 11.1x |

All four clean scenarios have significant headroom, confirming strong per-endpoint performance at 20 VUs.

**Conclusion:** Individual endpoint performance is excellent at 20 VUs. The heavy_aggregations failure is a concurrency artifact (scenario overlap) rather than a fundamental performance issue, but it reveals a real-world vulnerability: heavy analytical queries degrade under concurrent write pressure.

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
| p(95) | 34ms |
| p(90) | 29ms |
| Median (p50) | 16ms |
| Avg | 38ms |
| Max | 10.3s |
| Error rate | 0% |
| Checks passed | 100% (15,157/15,157) |
| Total requests | 15,158 |
| RPS | ~32 |
| Bookings created | 1,861 |

**Grafana observations:**
- Active VUs showed a textbook ramp shape: smooth climb from 0 to 50, flat hold at 50, clean ramp down to 0.
- RPS panel showed steady ~30-35 req/s during the hold phase, with the ramp shape mirroring VU count.
- Response Time Percentiles remained flat throughout the entire test. p50 stayed at ~16ms, p95 at ~34ms, with no upward trend even as VUs increased to 50. This flat profile indicates the system is well within its capacity.
- Error Rate showed a constant 0% line.

**Conclusion:** At normal production load (50 VUs), the system operates with massive headroom. Latencies are stable, error rate is zero, and CPU is barely utilized. The flat response time curve confirms there is no degradation as load increases within this range.

---

### B.2 Stress Test

**Purpose:** Progressive overload to find the degradation point. Unlike the load test (which stays within expected limits), the stress test intentionally pushes past capacity to observe how the system fails.

**Config:** Ramp 0 → 50 (1 min) → 50 → 100 (2 min) → 100 → 200 (2 min) → 200 → 300 (2 min) → 300 → 0 (1 min). Total stages: ~8 min. Actual duration: ~26 min (extended by in-flight request drain — see analysis).
**Thresholds:** p(95) < 1500ms, error rate < 10%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 353ms |
| p(90) | 307ms |
| Median (p50) | 163ms |
| Avg | 601ms |
| Max | 20.1 min (single stuck request) |
| Error rate | 0.54% (242 requests) |
| Checks passed | 99.47% (44,567/44,806) |
| Total requests | 44,810 |
| RPS | ~29 avg |
| Bookings | 5,410 success / 34 failed / 8 sold out |

**Why the test ran 26 min instead of 8 min:**

The 8-minute stage configuration defines when K6 stops creating new iterations. However, K6 waits for all in-flight HTTP requests to complete. The single longest request took **20.1 minutes** — a TCP connection that hung without receiving a response. This extended the total test wall-clock time to ~26 min. This is significant: it shows that the single worker can enter a state where connections remain open but unserviced for 20+ minutes.

**Grafana observations:**
- Active VUs showed the staircase ramp from 0 to 300 and back down.
- RPS peaked around 200 VUs, then decreased as more VUs competed for the single worker's event loop.
- Response Time Percentiles showed flat latency up to ~100 VUs, then increasing latency as VUs climbed to 200–300.
- Error Rate was near 0% through the 100 VU phase, with errors appearing primarily at 200+ VUs.
- CPU stayed below 20% — confirming the bottleneck is the single event loop, not CPU.

**Analysis:**

The stress test reveals the single worker's saturation curve:

1. **0–100 VUs:** System handles the load comfortably. Latency stable, no errors.
2. **100–200 VUs:** Latency increases but throughput continues to grow.
3. **200–300 VUs:** Connection saturation begins. New requests queue behind slow ones.
4. **Post-ramp-down:** A single stuck connection held for 20+ minutes, keeping the test open long after stages ended.

The low error rate (0.54%) and passing thresholds show the system degrades more gracefully than expected under *gradual* overload — the 30s graceful stop allows most in-flight requests to complete.

**Conclusion:** The single worker degrades gracefully under gradual overload (p95=353ms, 0.54% errors), but the stuck connection phenomenon (20+ minute max) reveals that individual requests can be stranded indefinitely under high concurrency. Practical ceiling: ~200 VUs before degradation becomes significant.

---

### B.3 Spike Test

**Purpose:** Test system response to a sudden traffic burst and — critically — whether the system recovers after the spike subsides. This simulates scenarios like a flash sale, viral event, or DDoS attack.

**Config:** 0 → 10 VUs (30s) → hold 10 (1 min) → spike 10 → 300 (10s) → hold 300 (30s) → drop 300 → 10 (10s) → hold 10 (1 min) → 0. Total: ~4 min.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | **60s (timeout)** |
| p(90) | 30.4s |
| Median (p50) | 27ms |
| Avg | 5.76s |
| Max | 60s |
| Error rate | 9.03% (261 requests) |
| Checks passed | 90.97% (2,628/2,890) |
| Total requests | 2,890 |
| RPS | ~12 (severely degraded) |
| Bookings | 331 success / 34 failed |

**Threshold result:** FAILED — p(95) crossed the 2000ms threshold.

**Grafana observations:**
- Active VUs showed the sharp spike: flat at 10, near-vertical jump to 300, hold for 30s, sharp drop back to 10.
- **THE CRITICAL FINDING: The system DID NOT RECOVER.** After VUs dropped from 300 back to 10, error rates continued and RPS stayed near zero. Even with only 10 VUs, the API was still struggling after the spike ended.
- Response Time vs VUs showed p95 jumping to 60s during the spike — and staying elevated after VUs dropped. The system never recovered within the test window.
- CPU dropped back to near 0% after the spike — the worker wasn't busy with computation. It was stuck processing a backlog of queued/timed-out connections.

**Comparison with Stress Test (same 300 VUs):**

| Metric | Stress (gradual ramp) | Spike (sudden burst) |
|--------|----------------------|---------------------|
| Time to reach 300 VUs | 7 minutes | 10 seconds |
| p(95) | 353ms | 60s (timeout) |
| Error rate | 0.54% | 9.03% |
| Recovery | Gradual drain | **No recovery** |
| Total requests | 44,810 | 2,890 |

**Analysis:**

The spike test exposes the single worker's most critical weakness: **inability to recover from sudden overload.** When load increases gradually (stress test), the event loop has time to process each wave of new connections. When 290 new connections arrive in 10 seconds:

1. The 300 VU burst creates ~300 simultaneous connections
2. The worker tries to context-switch between all of them
3. None complete quickly, so all start accumulating wait time
4. After the spike drops to 10 VUs, the worker still has a backlog of timed-out requests
5. New requests from the remaining 10 VUs get queued behind the backlog

**Conclusion:** This is the strongest argument for multi-worker deployment. A single worker cannot survive a sudden traffic spike and — more importantly — cannot self-recover after one. In production, this would require a manual restart or automatic health-check restart.

---

### B.4 Soak Test

**Purpose:** Long-running stability test to detect memory leaks, connection pool exhaustion, or gradual latency creep that only appears over extended periods.

**Config:** Ramp 0 → 30 VUs (1 min) → hold 30 VUs (30 min) → ramp down (1 min). Total: ~32 min.
**Thresholds:** p(95) < 700ms, error rate < 1%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 28ms |
| p(90) | 25ms |
| Median (p50) | 13ms |
| Avg | 16ms |
| Max | 359ms |
| Error rate | 0.00% |
| Checks passed | 100% (13,944/13,944) |
| Total requests | 13,945 |
| RPS | ~7 |
| Bookings created | 1,640 |
| Duration | 32 min |

**Grafana observations:**
- Active VUs showed a flat line at 30 VUs for the entire 30-minute hold period.
- **Response Time Percentiles stayed absolutely flat for 30 minutes.** p50 at ~13ms, p95 at ~28ms. No upward trend. This flat line proves there are no gradual resource leaks.
- RPS held steady at ~7 req/s throughout, with normal minor fluctuations.
- Error Rate showed 0% for the entire duration.
- Memory Usage showed a flat line — no growth over 30 minutes. This rules out memory leaks.

**Analysis:**

The soak test answers three critical questions:

1. **Memory leaks?** No. Memory usage was flat for 32 minutes.
2. **Connection pool exhaustion?** No. The pool handled 30 VUs continuously for 30 minutes without running out of connections.
3. **Latency creep?** No. p(95) stayed at 28ms from minute 1 to minute 32.

**Note:** Unlike the previous test run (2026-03-29), this run had no outlier requests (max was 359ms vs the previous 19m30s). The automated `run_tests.sh` ensures proper reseeding and API restarts between tests, eliminating lingering connections from prior test runs.

**Conclusion:** The single-worker API is rock solid under sustained moderate load. Its weakness is burst capacity (spike/stress), not endurance. For applications with predictable, steady traffic patterns, a single worker is perfectly adequate.

---

### B.5 Breakpoint Test

**Purpose:** Find the absolute maximum throughput using open-model load. Unlike closed-model tests (load, stress, spike) where VUs wait for responses before sending new requests, the open-model sends requests at a target rate regardless of response times.

**Config:** ramping-arrival-rate executor. Ramp from 10 to 500 iterations/s over 20 minutes. preAllocatedVUs = 50, maxVUs = 500. Auto-abort when p(95) > 5000ms.
**Thresholds:** p(95) < 5000ms with abortOnFail.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 19.3s |
| p(90) | 79ms |
| Median (p50) | 21ms |
| Avg | 2.97s |
| Max | 3.7 min |
| Error rate | 9.11% (3,729 requests) |
| Total requests | 40,926 |
| Peak RPS | ~39 avg |
| VUs at abort | 500 (maxVUs exhausted) |
| Dropped iterations | 118,359 |
| Bookings | 4,472 success / 428 failed |
| Duration | ~17.5 min (aborted before 20 min target) |

**Successful requests only:** avg 31ms, p(95) 83ms — showing that requests that completed were fast; the tail is dominated by timeouts.

**Grafana observations:**
- Active VUs showed a smooth ramp from 0 to 500, steepening as the system saturated (more VUs needed to attempt the target rate when responses were slow).
- RPS reached a ceiling, then collapsed as the system became overwhelmed. The sustained throughput ceiling before degradation is the key metric.
- Response Time Percentiles showed flat latency for the first several minutes, then staircase jumps as saturation cascaded.
- Error Rate climbed from 0% to increasingly higher levels in the final minutes before abort.
- CPU stayed below 20% — again confirming this is not a CPU bottleneck.
- Dropped iterations (118,359) means K6 wanted to send ~118K more requests but couldn't allocate enough VUs.

**Analysis:**

The breakpoint test identifies the single worker's hard ceiling under open-model conditions:

1. **Sustainable throughput:** The system maintained low latency for several minutes before degradation began, establishing the throughput ceiling.
2. **Collapse is rapid.** Once saturation begins, the cascade from "working" to "overwhelmed" takes only a few minutes.
3. **VU exhaustion.** K6 allocated all 500 maxVUs trying to meet the target rate.
4. **Successful requests stay fast.** The p(95) for successful responses (83ms) vs overall (19.3s) shows a bimodal distribution: requests either complete quickly or time out entirely.

**Conclusion:** The single worker's capacity ceiling is reached when the target request rate exceeds what the event loop can process. Beyond this, the system enters rapid cascade failure. This number becomes the key comparison metric for multi-worker tests.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Purpose:** Test PostgreSQL row-level locking (`SELECT ... FOR UPDATE` via SQLAlchemy's `with_for_update()`) under extreme contention. All 50 VUs simultaneously try to book the *same event* (event_id=1), creating maximum lock contention on a single database row.

**Config:** 50 VUs, 2 min duration. Each iteration: attempt to book event_id=1, then read event_id=1's details. Custom metric `contention_booking_latency` tracks booking-specific response times.
**Thresholds:** booking latency p(95) < 3000ms, error rate < 5%.

**Results:**

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 48ms |
| Booking latency avg | 20ms |
| Booking latency median | 14ms |
| HTTP p(95) | 40ms |
| HTTP avg | 18ms |
| Max | 624ms |
| Error rate | 0.00% |
| Checks passed | 100% (17,400/17,400) |
| Total requests | 17,402 |
| RPS | ~144 |
| Bookings success | 283 |
| Sold out (409) | 8,417 |
| Duration | 2 min |

**Grafana observations:**
- Active VUs showed a flat line at 50 VUs for 2 minutes.
- CPU spiked briefly at test start when all 50 VUs hit event_id=1 simultaneously and tickets were still available. Each booking requires: row lock acquisition → capacity check → booking insert → capacity decrement → commit. Once tickets sold out (~10-15 seconds in), CPU dropped because 409 "sold out" responses are cheap.
- Response time remained flat and low throughout — the locking overhead is minimal.

**Analysis:**

The contention test validates the correctness and performance of the pessimistic locking strategy:

1. **Correctness:** Exactly 283 bookings succeeded (matching the event's ticket capacity). Every subsequent attempt correctly received a 409 "sold out" response. No double-bookings, no overselling, no deadlocks.

2. **Lock performance:** Even with 50 VUs fighting over a single row, p(95) stayed at 48ms for bookings. The `with_for_update()` lock queue processes requests efficiently because each critical section (check capacity → insert → decrement) is very short.

3. **Two-phase behavior:** Phase 1 (tickets available, ~15s) involves heavy locking with actual writes. Phase 2 (sold out, ~105s) involves lightweight capacity checks returning 409.

**Conclusion:** The `with_for_update()` pessimistic locking strategy is highly effective. It maintains correctness under extreme contention (50 concurrent users, single event) with zero deadlocks and sub-50ms booking latency.

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
| p(95) | 38ms | 56ms |
| Median | — | — |
| Avg | 22ms | 22ms |
| Max | 223ms | 223ms |
| Error rate | 0% | 0% |
| Bookings created | 785 | 2,758 |

- **Total requests:** 16,053
- **Checks passed:** 100% (16,052/16,052)
- **Combined RPS:** ~43

**Analysis:**

| Metric | Read-heavy | Write-heavy | Ratio (W/R) |
|--------|-----------|-------------|-------------|
| p(95) | 38ms | 56ms | 1.47x |

1. **Write-heavy p95 is 1.5x slower.** Write operations need row locks (`SELECT ... FOR UPDATE`), transaction commits, and capacity validation. Reads are simple SELECT queries without exclusive locks.

2. **Both profiles are clean at 30 VUs.** Zero errors, stable latency, consistent RPS. The 1.5x penalty for write-heavy traffic is modest.

3. **The gap would widen at higher concurrency.** At 30 VUs, lock contention is minimal because writes are spread across 100 events. At 200+ VUs (like the stress test), write locks would queue more frequently.

**Conclusion:** Write-heavy traffic adds ~50% latency at p95 compared to read-heavy traffic at moderate load (30 VUs). The performance impact is measurable but modest, validating the pessimistic locking approach as a reasonable tradeoff between correctness and performance.

---

## System Behavior Under Failure

### Observed Failure Patterns

| Test | Peak VUs | API Status After | Recovery |
|------|----------|-----------------|----------|
| Load (50 VUs) | 50 | Healthy | Self-recovered |
| Stress (300 VUs gradual) | 300 | Strained, 20min stuck request | Self-recovered (slowly) |
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
- This motivates the multi-worker comparison — we expect the ceiling to increase proportionally with worker count.

---

## Key Conclusions — 1 Uvicorn Worker

### Performance Envelope

| Metric | Value | Context |
|--------|-------|---------|
| Comfortable capacity | 50 VUs / 32 RPS | p(95) < 34ms, 0% errors |
| Degradation point | 200+ VUs | Latency increases, stuck connections appear |
| Collapse point | 300 VUs sudden | System becomes unresponsive, no recovery |

### Architectural Strengths
1. **Excellent low-load performance:** Sub-34ms p(95) at 50 VUs
2. **Perfect stability:** 32-minute soak test with zero degradation, no outliers
3. **Correct concurrency control:** `with_for_update()` prevents double-booking with zero deadlocks
4. **No resource leaks:** Flat memory and latency curves over 32 minutes
5. **Graceful gradual degradation:** Stress test passed with 0.54% errors despite 300 VUs

### Architectural Weaknesses
1. **Single event loop bottleneck:** Limits concurrent connection handling regardless of CPU availability
2. **No spike recovery:** Sudden traffic bursts overwhelm the worker permanently
3. **Stuck connections:** Under high concurrency, individual requests can hang for 20+ minutes
4. **Non-linear degradation:** Performance collapses rapidly past the saturation point

### Implications for Multi-Worker Comparison
The multi-worker configurations (2w, 4w) should address the primary bottleneck (single event loop) by running independent Python processes. Expected improvements:
- Higher throughput ceiling (proportional to worker count)
- Better spike resilience (load distributed across workers)
- Faster recovery after overload (individual workers may survive even if some become saturated)
- Similar per-request latency at low load (the bottleneck only matters under high concurrency)
