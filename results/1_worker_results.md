# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** Run 1: 2026-03-31, Run 2: 2026-04-04
**Configuration:** Docker (FastAPI + PostgreSQL), 1 Uvicorn worker
**Seed data:** 1,000 users, 100 events, 2,000 bookings (re-seeded before each test via `run_tests.sh`)
**Monitoring:** K6 → Prometheus remote write → Grafana dashboard (live visualization)
**Machine:** Windows 11, 32 GiB RAM
**K6 output:** `--out experimental-prometheus-rw` with trend stats: p(50), p(90), p(95), p(99), avg, min, max
**Test runner:** Automated via `run_tests.sh` (re-seed → run → restart if crashed → 30s cool-down)
**Resource limits:** API 2 CPU / 1 GB, PostgreSQL 2 CPU / 1 GB, Prometheus 1 CPU / 512 MB

---

## Multi-Run Summary Table

| Test | Type | VUs | R1 p(95) | R2 p(95) | R1 Errors | R2 Errors | R1 RPS | R2 RPS | Status |
|------|------|-----|----------|----------|-----------|-----------|--------|--------|--------|
| Baseline | Smoke | 10 | 62ms | 45ms | 0% | 0% | 85 | 87 | PASS |
| Endpoint Benchmark | Isolation | 20 | 42–107ms* | ALL PASS | 0.10% | 0% | 25 | — | R1: PARTIAL FAIL, R2: PASS |
| Load | Normal load | 50 | 34ms | 29ms | 0% | 0% | 32 | 32 | PASS |
| Stress | Overload | 300 | 353ms | 457ms | 0.54% | 1.48% | 29 | 82 | PASS |
| Spike | Burst | 300 | 60s | 60s | 9.03% | 9.37% | 12 | 12 | **FAIL** (consistent) |
| Soak | Endurance | 30 | 28ms | 25ms | 0% | 0% | 7 | 23 | PASS |
| Breakpoint | Capacity | 500 | 19.3s | 60s | 9.11% | 5.04% | 39 | 56 | **FAIL** (consistent) |
| Contention | Locking | 50 | 48ms† | 42ms | 0% | 0% | 144 | 146 | PASS |
| Read vs Write (read) | Traffic profile | 30 | 38ms | 32ms | 0% | 0% | ~43 | ~43 | PASS |
| Read vs Write (write) | Traffic profile | 30 | 56ms | 32ms | 0% | 0% | ~43 | ~43 | PASS |
| Recovery | Recovery | 300 | — | 59,210ms | — | 5.13% | — | 16 | **FAIL** (R1 N/A) |

*Run 1 endpoint benchmark had scenario overlap causing heavy_aggregations failure; Run 2 used fixed 100s gaps — all pass.
†Contention p(95) is booking-specific `contention_booking_latency`.

---

## Multi-Run Variability Analysis

**Run 1** (2026-03-31) was the first complete test suite execution. **Run 2** (2026-04-04) was a re-run using the improved `run_tests.sh` automation with proper re-seeding and container restarts between tests.

### Stable Results (consistent across runs)
- **Load test:** p(95) 34ms → 29ms, 0% errors both runs. Very consistent.
- **Soak test:** p(95) 28ms → 25ms, 0% errors both runs. Stable latency.
- **Contention test:** Booking p(95) 48ms → 42ms. Consistent behavior.
- **Spike test:** Both runs FAIL with 60s timeout p(95), ~9% errors. Consistently bad.
- **Read vs Write:** Consistent low latency, 0% errors both runs.

### Changed Results (methodology or environment effects)
- **Stress test RPS:** 29 → 82. Run 1's stress test took 26 minutes (a single request hung for 20+ minutes, keeping the test open). Run 2 completed in 8.5 minutes as designed. The stuck connection in run 1 was an anomaly — run 2's RPS of 82 better reflects actual throughput.
- **Soak RPS:** 7 → 23. Run 1 may have had lingering state from prior tests. Run 2 used proper re-seeding via `run_tests.sh`, giving clean state. The 23 RPS figure is more reliable.
- **Load max:** 10.3s → 72ms. The run 1 outlier was an anomaly (single stuck request). Run 2 confirms clean behavior.
- **Endpoint Benchmark:** Run 1 had scenario overlap (70s gaps); Run 2 used fixed 100s gaps. Run 2 results are the correct benchmark.

### Conclusion on Stability
The 1-worker configuration produces **consistent results for low-to-moderate load tests** (baseline, load, soak, contention, read vs write). High-concurrency tests (stress, spike, breakpoint, recovery) show more variability due to the single event loop's sensitivity to connection queuing and timeout cascades.

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

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 34ms | 29ms |
| p(90) | 29ms | 25ms |
| Median (p50) | 16ms | 15ms |
| Avg | 38ms | 17ms |
| Max | 10.3s* | 72ms |
| Error rate | 0% | 0% |
| Total requests | 15,158 | 15,411 |
| RPS | ~32 | ~32 |
| Bookings created | 1,861 | 1,845 |

*Run 1 max of 10.3s was a single outlier (not reproduced in run 2). Run 2 confirms clean behavior with max=72ms.

**Analysis:** Both runs show excellent consistency: p(95) 29–34ms, 0% errors, ~32 RPS, ~15K requests. The run 1 max of 10.3s was an anomaly not reproduced in run 2.

**Conclusion:** At normal production load (50 VUs), the system operates with massive headroom. Latencies are stable (p95 ~30ms), error rate is zero, and the results are highly reproducible across runs.

---

### B.2 Stress Test

**Purpose:** Progressive overload to find the degradation point. Unlike the load test (which stays within expected limits), the stress test intentionally pushes past capacity to observe how the system fails.

**Config:** Ramp 0 → 50 (1 min) → 50 → 100 (2 min) → 100 → 200 (2 min) → 200 → 300 (2 min) → 300 → 0 (1 min). Total stages: ~8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 353ms | 457ms |
| p(90) | 307ms | 365ms |
| Median (p50) | 163ms | 174ms |
| Avg | 601ms | 1,103ms |
| Max | 20.1 min (stuck) | 60s (timeout) |
| Error rate | 0.54% | 1.48% |
| Total requests | 44,810 | 41,844 |
| RPS | ~29 | **~82** |
| Test duration | ~26 min | **~8.5 min** |
| Bookings | 5,410 / 34 fail | 4,883 / 10 sold out |
| Threshold | PASS | PASS |

**Run 1 anomaly — stuck connection:** Run 1 took 26 minutes because a single request hung for 20+ minutes without a response, keeping K6 waiting. This artificially depressed RPS (29) because the wall-clock time was 3x longer than the test stages. Run 2 completed in the expected 8.5 minutes with no stuck connections, yielding the more accurate RPS of 82.

**Run 2 is the reliable measurement.** The 82 RPS figure better reflects actual single-worker throughput under 300 VUs because the test completed in its designed timeframe.

**Analysis:**

The stress test reveals the single worker's saturation curve:

1. **0–100 VUs:** System handles the load comfortably. Latency stable, no errors.
2. **100–200 VUs:** Latency increases but throughput continues to grow.
3. **200–300 VUs:** Connection saturation begins. New requests queue behind slow ones.
4. **p(95) of 353–457ms** across both runs is well within the 1500ms threshold, showing the system degrades gracefully under gradual overload.

**Conclusion:** The single worker degrades gracefully under gradual overload (p95 ~400ms, ~1% errors, ~82 RPS). Practical ceiling: ~200 VUs before degradation becomes significant. The stuck connection phenomenon from run 1 (20+ minute max) was not reproduced in run 2, suggesting it was an anomaly rather than a systematic failure.

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

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 28ms | 25ms |
| p(90) | 25ms | 23ms |
| Median (p50) | 13ms | 13ms |
| Avg | 16ms | 15ms |
| Max | 359ms | 124ms |
| Error rate | 0.00% | 0.00% |
| Total requests | 13,945 | 44,217 |
| RPS | ~7 | **~23** |
| Bookings created | 1,640 | 5,393 |
| Duration | 32 min | 32 min |

**Note on RPS discrepancy:** Run 1's low RPS (7) is likely caused by lingering state from prior tests (pre-`run_tests.sh` automation). Run 2 used the automated test runner with proper re-seeding and container restarts, yielding the more accurate RPS of 23. The p(95) and error rates are consistent across both runs.

**Analysis:**

The soak test answers three critical questions consistently across both runs:

1. **Memory leaks?** No. Memory usage was flat for 32 minutes in both runs.
2. **Connection pool exhaustion?** No. The pool handled 30 VUs continuously without running out.
3. **Latency creep?** No. p(95) stayed at 25–28ms from minute 1 to minute 32.

**Conclusion:** The single-worker API is rock solid under sustained moderate load. Results are highly reproducible (p95 ~26ms, 0% errors). Its weakness is burst capacity (spike/stress), not endurance.

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

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| Booking latency p(95) | 48ms | 42ms |
| Booking latency avg | 20ms | 19ms |
| Booking latency median | 14ms | 13ms |
| HTTP p(95) | 40ms | 37ms |
| Max | 624ms | 605ms |
| Error rate | 0.00% | 0.00% |
| Total requests | 17,402 | 17,630 |
| RPS | ~144 | ~146 |
| Bookings success | 283 | 283 |
| Sold out (409) | 8,417 | 8,531 |

**Grafana observations:**
- Active VUs showed a flat line at 50 VUs for 2 minutes.
- CPU spiked briefly at test start when all 50 VUs hit event_id=1 simultaneously and tickets were still available. Each booking requires: row lock acquisition → capacity check → booking insert → capacity decrement → commit. Once tickets sold out (~10-15 seconds in), CPU dropped because 409 "sold out" responses are cheap.
- Response time remained flat and low throughout — the locking overhead is minimal.

**Analysis:**

The contention test validates the correctness and performance of the pessimistic locking strategy:

1. **Correctness:** Exactly 283 bookings succeeded (matching the event's ticket capacity). Every subsequent attempt correctly received a 409 "sold out" response. No double-bookings, no overselling, no deadlocks.

2. **Lock performance:** Even with 50 VUs fighting over a single row, p(95) stayed at 42–48ms for bookings across both runs. The `with_for_update()` lock queue processes requests efficiently because each critical section (check capacity → insert → decrement) is very short.

3. **Two-phase behavior:** Phase 1 (tickets available, ~15s) involves heavy locking with actual writes. Phase 2 (sold out, ~105s) involves lightweight capacity checks returning 409.

**Conclusion:** Highly reproducible across runs. The `with_for_update()` pessimistic locking strategy maintains correctness (exactly 283 bookings, zero deadlocks) with sub-50ms booking latency. RPS is consistent at ~145.

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

**Run 1 Results:**

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 38ms | 56ms |
| Avg | 22ms | 22ms |
| Error rate | 0% | 0% |
| Bookings | 785 | 2,758 |

**Run 2 Results:**

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | ~32ms | ~32ms |
| Avg | 19ms | 19ms |
| Error rate | 0% | 0% |
| Bookings | 807 | 2,892 |

- **Combined RPS:** ~43 (both runs)
- **Checks passed:** 100% (both runs)

**Analysis:**

| Config | Read p(95) | Write p(95) | Write/Read Ratio |
|--------|-----------|-------------|------------------|
| Run 1 | 38ms | 56ms | 1.47x |
| Run 2 | ~32ms | ~32ms | ~1.0x |

Run 1 showed a clear 1.47x write penalty; run 2 shows near-parity. The difference may reflect cleaner starting state in run 2 (proper re-seeding). Both runs confirm the system handles 30 VUs with zero errors.

**Conclusion:** Write-heavy traffic adds 0–50% latency at p95 compared to read-heavy traffic at moderate load (30 VUs). The impact is modest and validates the pessimistic locking approach.

---

## System Behavior Under Failure

### Observed Failure Patterns

| Test | Peak VUs | API Status After | Recovery | Consistent? |
|------|----------|-----------------|----------|-------------|
| Load (50 VUs) | 50 | Healthy | N/A | Yes |
| Stress (300 VUs gradual) | 300 | Strained | Self-recovered | Yes (PASS both) |
| Spike (300 VUs sudden) | 300 | Unresponsive | Required restart | Yes (FAIL both) |
| Breakpoint (500 VUs) | 500 | Crashed | Required restart | Yes (FAIL both) |
| Soak (30 VUs, 32 min) | 30 | Healthy | N/A | Yes |
| Recovery (300 VU spike) | 300 | Unresponsive | Timeout cascade | Run 2 only (FAIL) |

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

### Performance Envelope (Multi-Run)

| Metric | Value | Context | Reproducible? |
|--------|-------|---------|---------------|
| Comfortable capacity | 50 VUs / 32 RPS | p(95) 29–34ms, 0% errors | Yes |
| Stress capacity | 300 VUs / ~82 RPS | p(95) 353–457ms, ~1% errors | Yes (PASS both) |
| Collapse point | 300 VUs sudden | Spike FAIL, Recovery FAIL | Yes (FAIL both) |

### Architectural Strengths
1. **Excellent low-load performance:** Sub-34ms p(95) at 50 VUs (consistent across runs)
2. **Perfect stability:** 32-minute soak test with zero degradation (consistent)
3. **Correct concurrency control:** `with_for_update()` prevents double-booking with zero deadlocks (consistent)
4. **No resource leaks:** Flat memory and latency curves over 32 minutes (consistent)
5. **Graceful gradual degradation:** Stress test passed both runs with <1.5% errors despite 300 VUs

### Architectural Weaknesses
1. **Single event loop bottleneck:** Limits concurrent connection handling regardless of CPU availability
2. **No spike recovery:** Sudden traffic bursts overwhelm the worker permanently (consistent across runs)
3. **Non-linear degradation:** Performance collapses rapidly past the saturation point

### Implications for Multi-Worker Comparison
The multi-worker configurations (2w, 4w) should address the primary bottleneck (single event loop) by running independent Python processes. Expected improvements:
- Higher throughput ceiling (proportional to worker count)
- Better spike resilience (load distributed across workers)
- Faster recovery after overload (individual workers may survive even if some become saturated)
- Similar per-request latency at low load (the bottleneck only matters under high concurrency)
