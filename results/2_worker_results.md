# K6 Performance Test Results — 2 Uvicorn Workers

**Date:** 2026-04-04
**Configuration:** Docker (FastAPI + PostgreSQL), 2 Uvicorn workers
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
| Baseline | Smoke | 10 | 32s | 79ms | 58ms | 123ms* | 0% | 47 | PASS |
| Endpoint Benchmark | Isolation | 20 | ~7.7min | 51–74ms | — | 33ms | 0% | 55 | PASS |
| Load | Normal load | 50 | 8min | 29ms | 15ms | 17ms | 0% | 32 | PASS |
| Stress | Overload | 300 | 8min | 643ms | 87ms | 331ms | 0.19% | 171 | PASS |
| Spike | Burst | 300 | ~15min | 1,148ms | 648ms | 570ms | 0% | 13 | PASS |
| Soak | Endurance | 30 | 32min | 28ms | 14ms | 22ms | 0% | 23 | PASS |
| Breakpoint | Capacity | 500 | ~13min | 30.4s | 18ms | 2.9s | 5.86% | 43 | FAIL |
| Contention | Locking | 50 | 2min | 76ms | 21ms | 32ms | 0% | 122 | PASS |
| Read vs Write (read) | Traffic profile | 30 | 6.4min | 37ms | 19ms | 21ms | 0% | ~27 | PASS |
| Read vs Write (write) | Traffic profile | 30 | 6.4min | 40ms | 21ms | 26ms | 0% | ~27 | PASS |
| Recovery | Recovery | 300 | 6.2min | 667ms | 34ms | 590ms | 0.60% | 57 | PASS |

**Overall: 9 passed, 1 failed (breakpoint). Spike test now passes with 2 workers.**

*Baseline avg inflated by single 10s network outlier; server processing avg was 17ms.

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Purpose:** Verify all endpoints are functional before heavy testing.

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 79ms |
| p(90) | 72ms |
| Avg response time | 123ms* |
| Median (p50) | 58ms |
| Max | 10.1s* |
| Server processing (waiting) p(95) | 35ms |
| Server processing (waiting) avg | 17ms |
| Error rate | 0% |
| Checks passed | 100% (2,033/2,033) |
| Total requests | 1,499 |
| RPS | ~47 |
| Iterations | 107 (3.3/s) |

*A single request experienced a 10s network send delay, inflating the avg and max. The server processing time (http_req_waiting) was unaffected: avg 17ms, p95 35ms.

**Comparison with 1 worker:**

| Metric | 1w | 2w |
|--------|----|----|
| p(95) | 62ms | 79ms |
| Median | 22ms | 58ms |
| RPS | 85 | 47 |

**Analysis:** At low concurrency (10 VUs), the 2-worker configuration shows slightly higher latency and lower throughput compared to 1 worker. This is expected: with only 10 concurrent connections, a single event loop handles them efficiently. The second worker adds inter-process overhead (OS scheduling, separate database connection pools) without benefit. The real advantage of multiple workers emerges under higher concurrency.

**Conclusion:** All endpoints healthy and responsive. The baseline establishes that 2 workers add minor overhead at low load — a tradeoff that pays off under high concurrency (see stress, spike, and recovery tests).

---

### A.2 Endpoint Benchmark

**Purpose:** Isolate each endpoint category under controlled load. Each scenario runs sequentially (via `startTime` offset with 100s gaps) to prevent overlap.

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario, 100s gap between scenarios. Total: ~7.7 min.

**Note:** This test uses the fixed version with 100s gaps (vs the 70s gaps in the 1w run that caused scenario overlap and heavy_aggregations failure).

**Results:**

| Scenario | Endpoints | p(95) | Avg | Threshold | Result |
|----------|-----------|-------|-----|-----------|--------|
| Light Reads | GET /health, /users/{id}, /events/{id}, /bookings/{id} | 68ms | 46ms | <200ms | PASS |
| List Reads | GET /users/, /events/, /bookings/ (limit=100) | 51ms | 21ms | <500ms | PASS |
| Search & Filter | GET /events/search, /events/upcoming, /users/{id}/bookings, /events/{id}/bookings | 58ms | 25ms | <500ms | PASS |
| Writes | POST /bookings/, PATCH /bookings/{id}/cancel | 71ms | 44ms | <1000ms | PASS |
| Heavy Aggregations | GET /events/{id}/stats, /events/popular, /stats | 74ms | 32ms | <1500ms | PASS |

- **Total requests:** 25,470
- **Checks passed:** 100% (25,469/25,469)
- **Error rate:** 0%
- **Total RPS:** ~55

**All 5 scenarios passed**, including heavy_aggregations which failed in the 1w run due to scenario overlap. The 100s startTime gap fix ensures no concurrent execution between scenarios.

**Conclusion:** Per-endpoint performance is excellent at 20 VUs with 2 workers. Heavy aggregations now completes cleanly in 74ms p(95) — well within the 1500ms threshold.

---

## Phase B — Standard Test Types (Mixed Realistic Traffic)

All Phase B tests use the same weighted traffic distribution:

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

---

### B.1 Load Test

**Purpose:** Simulate normal-to-peak traffic and verify the system handles expected production load.

**Config:** Ramp 0 → 50 VUs (2 min) → hold 50 VUs (5 min) → ramp down to 0 (1 min). Total: ~8 min.
**Thresholds:** p(95) < 500ms, p(99) < 1000ms, error rate < 1%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 29ms |
| p(90) | 25ms |
| Median (p50) | 15ms |
| Avg | 17ms |
| Max | 155ms |
| Error rate | 0% |
| Checks passed | 100% (15,430/15,430) |
| Total requests | 15,431 |
| RPS | ~32 |
| Bookings created | 1,951 |

**Comparison with 1 worker:**

| Metric | 1w | 2w | Change |
|--------|----|----|--------|
| p(95) | 34ms | 29ms | -15% (better) |
| Avg | 38ms | 17ms | -55% (better) |
| Max | 10.3s | 155ms | -98% (better) |
| Error rate | 0% | 0% | Same |

**Analysis:** The 2-worker configuration eliminates the long-tail latency seen in 1w (max dropped from 10.3s to 155ms). The p(95) improved by 15% and avg by 55%. At 50 VUs, both configurations handle the load without errors, but 2 workers provides a more consistent experience with no outliers.

**Conclusion:** Normal production load is handled effortlessly. The second worker eliminates tail latency spikes that occasionally occurred with 1 worker.

---

### B.2 Stress Test

**Purpose:** Progressive overload to find the degradation point.

**Config:** Ramp 0 → 50 (1 min) → 50 → 100 (2 min) → 100 → 200 (2 min) → 200 → 300 (2 min) → 300 → 0 (1 min). Total: ~8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 643ms |
| p(90) | 495ms |
| Median (p50) | 87ms |
| Avg | 331ms |
| Max | 60s |
| Error rate | 0.19% (159 requests) |
| Checks passed | 99.81% (81,867/82,026) |
| Total requests | 82,027 |
| RPS | ~171 |
| Bookings | 9,604 success / 19 failed / 169 sold out |

**Comparison with 1 worker:**

| Metric | 1w | 2w | Change |
|--------|----|----|--------|
| Total requests | 44,810 | 82,027 | +83% |
| RPS | 29 | 171 | **+490%** |
| Error rate | 0.54% | 0.19% | -65% |
| Max | 20.1 min | 60s | No stuck connections |
| Test duration | 26 min | 8 min | Completed in expected time |
| Bookings | 5,410 | 9,604 | +78% |

**Analysis:**

The stress test reveals the most dramatic improvement from adding a second worker:

1. **Throughput increased 5.9x** (171 vs 29 RPS). With two event loops, twice as many connections can be processed concurrently.
2. **No stuck connections.** The 1w stress test had a single request stuck for 20.1 minutes, extending the test from 8 to 26 minutes. With 2 workers, the max request time was 60s (the timeout), and the test completed in the expected 8 minutes.
3. **Lower error rate** (0.19% vs 0.54%) despite processing nearly 2x the requests.
4. **The p(95) is higher** (643ms vs 353ms), but this is because the 2w system actually processes requests that 1w was dropping or queueing indefinitely. Higher p95 with 5.9x throughput is a net positive.

**Conclusion:** Two workers fundamentally change the stress test outcome. The system handles 300 VUs with nearly 6x the throughput, no stuck connections, and completes in the expected timeframe. The single-worker bottleneck (event loop saturation) is effectively doubled.

---

### B.3 Spike Test

**Purpose:** Test system response to sudden traffic burst and recovery capability.

**Config:** 0 → 10 VUs (30s) → hold 10 (1 min) → spike 10 → 300 (10s) → hold 300 (30s) → drop 300 → 10 (10s) → hold 10 (1 min) → 0. Total stages: ~4 min.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 1,148ms |
| p(90) | 1,045ms |
| Median (p50) | 648ms |
| Avg | 570ms |
| Max | 2,281ms |
| Error rate | 0% |
| Checks passed | 100% (12,133/12,133) |
| Total requests | 12,134 |
| RPS | ~13 |
| Bookings | 1,438 success |

**Threshold result:** PASSED (p(95) = 1,148ms < 2,000ms)

**Comparison with 1 worker:**

| Metric | 1w | 2w | Change |
|--------|----|----|--------|
| p(95) | 60s (timeout) | 1,148ms | **-98%** |
| Max | 60s | 2.3s | -96% |
| Error rate | 9.03% | 0% | **-100%** |
| Threshold | FAIL | **PASS** | Fixed |
| Total requests | 2,890 | 12,134 | +320% |
| API after test | Unresponsive | Alive | Survived |

**This is the headline improvement for the 2-worker configuration.**

**Analysis:**

The spike test was the single-worker's worst failure: 60s timeouts, 9% errors, and the API became unresponsive with no self-recovery. With 2 workers:

1. **The system survived the spike.** No crashes, no unresponsive state, 0% errors.
2. **p(95) dropped from 60s to 1.1s** — a 52x improvement.
3. **The system recovered after the spike.** Unlike 1w where the API never recovered within the test window, 2w handled the post-spike observation period with functional (if elevated) latency.
4. **4.2x more requests processed.** The 1w system was so overwhelmed it could barely serve any requests. The 2w system continued operating through the spike.

**Why 2 workers survive the spike:**

When 290 connections arrive in 10 seconds, two event loops can split the load. Each worker handles ~150 connections instead of the full 300. While each worker is under heavy load, neither enters the catastrophic cascade failure that a single worker experiences. The connection queue per worker stays manageable, preventing the self-reinforcing timeout spiral.

**Conclusion:** Adding a second worker transforms the spike test from a catastrophic failure to a passing test. This is the strongest evidence that multi-worker deployment is essential for systems that may experience sudden traffic bursts.

---

### B.4 Soak Test

**Purpose:** Long-running stability test to detect memory leaks, connection pool exhaustion, or gradual latency creep.

**Config:** Ramp 0 → 30 VUs (1 min) → hold 30 VUs (30 min) → ramp down (1 min). Total: ~32 min.
**Thresholds:** p(95) < 700ms, error rate < 1%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 28ms |
| p(90) | 25ms |
| Median (p50) | 14ms |
| Avg | 22ms |
| Max | 10.3s* |
| Error rate | 0.00% |
| Checks passed | 100% (43,774/43,774) |
| Total requests | 43,775 |
| RPS | ~23 |
| Bookings created | 5,190 |
| Sold out | 11 |
| Duration | 32 min |

*Single outlier (10.3s) in http_req_sending; server processing max was 130ms.

**Comparison with 1 worker:**

| Metric | 1w | 2w | Change |
|--------|----|----|--------|
| p(95) | 28ms | 28ms | Same |
| Avg | 16ms | 22ms | +38% |
| RPS | 7 | 23 | **+229%** |
| Total requests | 13,945 | 43,775 | +214% |
| Error rate | 0% | 0% | Same |

**Analysis:**

1. **p(95) is identical** (28ms for both configurations). At 30 VUs, both 1w and 2w handle the load comfortably — neither event loop is stressed.
2. **RPS increased 3.3x** with 2 workers. With two event loops processing requests, iterations complete faster, allowing more total throughput at the same VU count.
3. **No resource leaks.** Latency remained flat for the full 32 minutes. No memory growth, no connection pool exhaustion.
4. **The 3.3x RPS improvement** at 30 VUs is notable. Even at moderate load, two workers provide meaningful throughput gains because request processing is distributed across two event loops.

**Conclusion:** Rock-solid stability over 32 minutes. The soak test confirms no resource leaks with 2 workers and reveals a significant throughput bonus (3.3x) even at moderate concurrency.

---

### B.5 Breakpoint Test

**Purpose:** Find the absolute maximum throughput using open-model load (ramping-arrival-rate).

**Config:** Ramp from 10 to 500 iterations/s over 20 minutes. preAllocatedVUs = 50, maxVUs = 500. Auto-abort when p(95) > 5000ms.
**Thresholds:** p(95) < 5000ms with abortOnFail.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 30.4s |
| p(90) | 66ms |
| Median (p50) | 18ms |
| Avg | 2.9s |
| Max | 60s (timeout) |
| Error rate | 5.86% (1,979 requests) |
| Successful request p(95) | 69ms |
| Total requests | 33,758 |
| Peak RPS | ~43 |
| VUs at abort | 500 |
| Dropped iterations | 42,746 |
| Bookings | 3,780 success / 227 failed |
| Duration | ~13.2 min (aborted) |

**Threshold result:** FAILED — p(95) = 30.4s > 5000ms

**Comparison with 1 worker:**

| Metric | 1w | 2w | Change |
|--------|----|----|--------|
| Duration before abort | 17.5 min | 13.2 min | Earlier abort |
| p(95) | 19.3s | 30.4s | Higher at failure |
| Error rate | 9.11% | 5.86% | -36% (better) |
| Dropped iterations | 118,359 | 42,746 | -64% (better) |
| Successful p(95) | 83ms | 69ms | -17% (better) |

**Analysis:**

1. **Fewer dropped iterations** (42,746 vs 118,359) means 2w kept up with the target arrival rate longer before being overwhelmed.
2. **Lower error rate** (5.86% vs 9.11%) shows the system handles more load before errors appear.
3. **The p(95) is higher** (30.4s vs 19.3s) because the system attempted to process more requests before aborting, accumulating a larger backlog when it finally collapsed.
4. **Earlier abort** (13 min vs 17 min) indicates the collapse, when it happens, is sharper — the system pushes harder and then hits a wall.

**Conclusion:** Both configurations ultimately fail the breakpoint test, confirming that 2 workers are not sufficient to handle 500 iter/s sustained load. However, 2w handles 64% fewer dropped iterations and has 36% fewer errors, showing meaningful capacity improvement. The capacity ceiling remains limited by having only 2 event loops for 500+ concurrent connections.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Purpose:** Test PostgreSQL row-level locking under extreme contention. All 50 VUs simultaneously book the same event (event_id=1).

**Config:** 50 VUs, 2 min duration. Custom metric `contention_booking_latency` tracks booking-specific response times.
**Thresholds:** booking latency p(95) < 3000ms, error rate < 5%.

**Results:**

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 76ms |
| Booking latency avg | 32ms |
| Booking latency median | 21ms |
| Booking latency max | 685ms |
| Error rate | 0.00% |
| Checks passed | 100% (15,020/15,020) |
| Total requests | 15,022 |
| RPS | ~122 |
| Bookings success | 283 |
| Sold out (409) | 7,227 |
| Initial tickets | 283 |

**Comparison with 1 worker:**

| Metric | 1w | 2w | Change |
|--------|----|----|--------|
| Booking latency p(95) | 48ms | 76ms | +58% (worse) |
| Booking latency avg | 20ms | 32ms | +60% (worse) |
| RPS | 144 | 122 | -15% (worse) |
| Error rate | 0% | 0% | Same |
| Bookings success | 283 | 283 | Same (correct) |

**Analysis:**

The contention test is the one scenario where 2 workers performs **worse** than 1 worker. This is an important finding:

1. **Database lock contention increases.** With 1 worker, all booking requests are serialized through a single event loop before reaching PostgreSQL. Requests naturally queue at the application layer, reducing concurrent lock acquisition. With 2 workers, both processes send booking requests to PostgreSQL simultaneously, doubling the actual database-level lock contention on `event_id=1`.

2. **Correctness is maintained.** Exactly 283 bookings succeeded (matching ticket capacity), zero double-bookings, zero deadlocks. The `with_for_update()` strategy works correctly regardless of worker count.

3. **The performance impact is modest.** 76ms p(95) is still well within the 3000ms threshold — 39x headroom. The increase from 48ms to 76ms is measurable but not problematic.

**Key thesis insight:** More workers doesn't always mean better performance. For single-row contention patterns, additional workers increase database lock contention. This is because the bottleneck shifts from the application layer (event loop) to the database layer (row locks). The correct optimization for this pattern is reducing lock hold time, not adding workers.

**Conclusion:** Locking correctness is perfect with 2 workers. The 58% increase in booking latency demonstrates that multi-worker deployment increases database contention for single-resource access patterns — an important architectural consideration.

---

### C.2 Read vs Write Test

**Purpose:** Compare system behavior under read-heavy vs write-heavy traffic.

**Config:** Two sequential scenarios at 30 VUs, 3 min each:

| Scenario | Profile | Operations |
|----------|---------|------------|
| `read_heavy` | 90% reads / 10% writes | Browse events, view event, search, list users, global stats, create booking |
| `write_heavy` | 40% reads / 60% writes | Browse events, view event, create booking, cancel booking |

**Thresholds:** read_heavy p(95) < 500ms, write_heavy p(95) < 1500ms, error rate < 5%.

**Results:**

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 37ms | 40ms |
| Median | 19ms | 21ms |
| Avg | 21ms | 26ms |
| Max | 146ms | 508ms |
| Error rate | 0% | 0% |
| Bookings created | 798 | 843 |

- **Total requests:** 10,302
- **Checks passed:** 100% (10,301/10,301)
- **Combined RPS:** ~27

**Comparison with 1 worker:**

| Metric | 1w read | 2w read | 1w write | 2w write |
|--------|---------|---------|----------|----------|
| p(95) | 38ms | 37ms | 56ms | 40ms |
| Avg | 22ms | 21ms | 22ms | 26ms |

**Analysis:**

1. **Write-heavy p(95) improved significantly** — from 56ms (1w) to 40ms (2w), a 29% reduction. With two workers, write transactions (which include row locks and commits) are distributed across two processes, reducing per-worker transaction overhead.

2. **Read-heavy performance is unchanged** — 37ms vs 38ms. Reads were never a bottleneck at 30 VUs.

3. **The read/write gap narrowed.** In 1w, write-heavy was 1.47x slower than read-heavy (56ms vs 38ms). In 2w, write-heavy is only 1.08x slower (40ms vs 37ms). The second worker almost eliminates the write penalty at moderate load.

**Conclusion:** Two workers significantly improve write-heavy performance, nearly closing the gap with read-heavy traffic. This confirms that write operations benefit more from additional workers than reads do at moderate concurrency.

---

### C.3 Recovery Test

**Purpose:** Measure time-to-recovery after sudden overload. Unlike the spike test (which focuses on behavior during the spike), this test has a long post-spike observation window.

**Config:** 1 min baseline (30 VUs) → 10s spike to 300 VUs → 30s hold at 300 → 10s drop to 30 → 4 min observation (30 VUs) → 20s ramp down. Total: ~6 min.
**Thresholds:** p(95) < 10,000ms, error rate < 30%, checks > 70%.

**Results:**

| Metric | Value |
|--------|-------|
| p(95) | 667ms |
| p(90) | 501ms |
| Median (p50) | 34ms |
| Avg | 590ms |
| Max | 60s (timeout) |
| Error rate | 0.60% (126 requests) |
| Checks passed | 99.40% (20,931/21,057) |
| Total requests | 21,058 |
| RPS | ~57 |
| Bookings | 2,540 success / 20 failed |

**Analysis:**

1. **The system recovered.** Despite the 300 VU spike, the API continued serving requests throughout and returned to normal operation during the 4-minute observation window.

2. **Error rate was minimal** (0.60%) — errors occurred during the spike peak, not during recovery.

3. **Median of 34ms** shows that most requests (during baseline and post-recovery) were fast. The elevated p(95) of 667ms and avg of 590ms reflect the spike period dragging up the overall statistics.

4. **Max of 60s** indicates some requests during the spike hit the timeout, but this did not cascade into system failure.

**Key thesis metric:** The Grafana time-series graph for this test is critical. The recovery curve — how quickly p95 returns from spike levels to baseline levels — is the primary comparison metric across 1w/2w/4w configurations.

**Conclusion:** With 2 workers, the system survives a 300 VU spike and recovers to normal operation. The recovery test passed all thresholds comfortably.

---

## System Behavior Under Failure

### Observed Failure Patterns

| Test | Peak VUs | API Status After | Recovery |
|------|----------|-----------------|----------|
| Load (50 VUs) | 50 | Healthy | N/A (no stress) |
| Stress (300 VUs gradual) | 300 | Healthy | Self-recovered |
| Spike (300 VUs sudden) | 300 | Alive, elevated latency | Self-recovered |
| Breakpoint (500 VUs) | 500 | Degraded | Required restart |
| Soak (30 VUs, 32 min) | 30 | Healthy | N/A |
| Recovery (300 VU spike) | 300 | Alive | Self-recovered |

### Comparison with 1 Worker

| Test | 1w Recovery | 2w Recovery |
|------|-------------|-------------|
| Stress (300 VUs) | 20 min stuck request | Clean completion |
| Spike (300 VUs) | **No recovery** (required restart) | **Self-recovered** |
| Breakpoint (500 VUs) | Crashed | Required restart |

The most significant behavioral change: **the spike test no longer kills the API.** With 1 worker, a sudden 300 VU burst caused permanent unresponsiveness. With 2 workers, the system survives and recovers.

### Root Cause

Two Uvicorn workers run two independent Python asyncio event loops. When concurrent connections spike:

1. **Load distribution** — the OS distributes incoming connections across both workers
2. **Independent failure domains** — if one worker's event loop becomes saturated, the other can still process requests
3. **Doubled connection capacity** — each worker handles its own connection queue, effectively doubling the total concurrent connection capacity
4. **No shared state** — workers don't share the event loop, so one worker's backlog doesn't affect the other

The bottleneck is still concurrency (not CPU), but two event loops provide enough capacity to survive 300 VU spikes that overwhelm a single worker.

---

## 1 Worker vs 2 Worker Comparison

### Summary

| Metric | 1w | 2w | Improvement |
|--------|----|----|-------------|
| Tests passed | 7/9* | 9/10 | +2 |
| Baseline p(95) | 62ms | 79ms | -27% (overhead) |
| Load p(95) | 34ms | 29ms | +15% |
| Load max | 10.3s | 155ms | +98% |
| Stress RPS | 29 | 171 | **+490%** |
| Stress errors | 0.54% | 0.19% | +65% |
| Spike p(95) | 60s | 1.1s | **+98%** |
| Spike errors | 9.03% | 0% | **+100%** |
| Spike result | FAIL | PASS | Fixed |
| Soak p(95) | 28ms | 28ms | Same |
| Soak RPS | 7 | 23 | +229% |
| Breakpoint errors | 9.11% | 5.86% | +36% |
| Contention p(95) | 48ms | 76ms | **-58% (worse)** |
| Write-heavy p(95) | 56ms | 40ms | +29% |

*1w had 9 tests total (no recovery test); spike FAIL + endpoint benchmark PARTIAL FAIL + breakpoint ABORT.

### Where 2 Workers Helps Most

1. **Spike resilience** — the single biggest improvement. System goes from catastrophic failure to passing.
2. **Stress throughput** — 5.9x RPS increase, enabling the system to serve far more users under overload.
3. **Tail latency elimination** — no more 10s+ outliers in normal load tests.
4. **Recovery capability** — system self-recovers after traffic bursts instead of requiring restarts.

### Where 2 Workers Doesn't Help (or Hurts)

1. **Low-concurrency overhead** — baseline shows 27% higher p(95) at 10 VUs.
2. **Single-row contention** — 58% higher booking latency in contention test due to increased database lock competition.
3. **Soak stability** — identical p(95) at 30 VUs (28ms). Stability was already perfect with 1 worker.

### Scaling Efficiency

| Metric | Scaling Factor (2w/1w) | Linear (ideal) |
|--------|----------------------|-----------------|
| Stress RPS | 5.9x | 2.0x |
| Soak RPS | 3.3x | 2.0x |
| Spike survival | 0% → 100% | N/A |

The stress test RPS scaling (5.9x) exceeds the theoretical 2x from doubling workers. This super-linear scaling occurs because 1w was severely bottlenecked — the single event loop was spending most of its time context-switching between 300 connections rather than doing useful work. With 2 workers handling 150 connections each, both operate more efficiently.

---

## Key Conclusions — 2 Uvicorn Workers

### Performance Envelope

| Metric | Value | Context |
|--------|-------|---------|
| Comfortable capacity | 50 VUs / 32 RPS | p(95) < 29ms, 0% errors |
| Stress capacity | 300 VUs / 171 RPS | p(95) < 643ms, 0.19% errors |
| Spike survival | 300 VUs sudden | p(95) = 1.1s, 0% errors, self-recovery |
| Collapse point | 500 VUs sustained | Breakpoint test fails at ~13 min |

### Architectural Strengths
1. **Spike resilience** — survives 300 VU sudden bursts that killed 1 worker
2. **Self-recovery** — returns to normal after overload without manual intervention
3. **5.9x stress throughput** — handles far more concurrent users under peak load
4. **Tail latency elimination** — no stuck connections or 10s+ outliers
5. **Correct concurrency control** — `with_for_update()` works correctly across both workers

### Architectural Weaknesses
1. **Increased database contention** — multi-worker amplifies row-level lock competition
2. **Low-load overhead** — ~27% higher latency at 10 VUs vs 1 worker
3. **Still limited by event loop count** — 500+ sustained VUs overwhelm both workers
4. **Breakpoint still fails** — 2 event loops insufficient for open-model 500 iter/s load

### Implications for 4-Worker Test
Based on the 2w results, the 4-worker configuration should:
- Further improve spike/stress resilience (4 independent failure domains)
- Increase the breakpoint ceiling (potentially passing or lasting longer)
- Show further increased contention latency (4 processes competing for locks)
- Provide diminishing returns at low load (more overhead, same workload)
- Reveal whether scaling is still super-linear or approaching the database bottleneck
