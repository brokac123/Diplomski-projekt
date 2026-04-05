# K6 Performance Test Results — 2 Uvicorn Workers

**Date:** Run 1: 2026-04-04, Run 2: 2026-04-04/05
**Configuration:** Docker (FastAPI + PostgreSQL), 2 Uvicorn workers
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
| Baseline | Smoke | 10 | 79ms* | 42ms | 0% | 0% | 47 | 90 | PASS |
| Endpoint Benchmark | Isolation | 20 | 51–74ms | 25–72ms | 0% | 0% | 55 | 59 | PASS |
| Load | Normal load | 50 | 29ms | 32ms | 0% | 0% | 32 | 32 | PASS |
| Stress | Overload | 300 | 643ms | 477ms | 0.19% | 1.71% | 171 | **76** | PASS |
| Spike | Burst | 300 | 1,148ms | **60,001ms** | 0% | **9.16%** | 13 | 12 | **INCONSISTENT** (R1 PASS, R2 FAIL) |
| Soak | Endurance | 30 | 28ms | 31ms | 0% | 0% | 23 | 23 | PASS |
| Breakpoint | Capacity | 500 | 30.4s | 31.1s | 5.86% | 5.68% | 43 | 43 | FAIL (consistent) |
| Contention | Locking | 50 | 76ms | 141ms | 0% | 0% | 122 | 135 | PASS |
| Read vs Write (read) | Traffic profile | 30 | 37ms | 55ms | 0% | 0% | ~27 | ~43 | PASS |
| Read vs Write (write) | Traffic profile | 30 | 40ms | 74ms | 0% | 0% | ~27 | ~43 | PASS |
| Recovery | Recovery | 300 | 667ms | **59,996ms** | 0.60% | **5.44%** | 57 | 15 | **INCONSISTENT** (R1 PASS, R2 FAIL) |

*Run 1 baseline avg inflated by single 10s network outlier; server processing avg was 17ms.

**Overall: Stable tests pass consistently. Spike and recovery tests are NOT reproducible — passed in run 1, failed in run 2.**

---

## Multi-Run Variability Analysis

### Stable Results (consistent across runs)
- **Load test:** p(95) 29–32ms, 0% errors, 32 RPS. Extremely consistent.
- **Soak test:** p(95) 28–31ms, 0% errors, 23 RPS. Rock solid.
- **Breakpoint test:** Both runs FAIL with ~30s p(95), ~5.8% errors. Consistent.
- **Endpoint benchmark:** All scenarios PASS both runs.

### Critical Inconsistencies

**Spike test (R1: PASS, R2: FAIL):** The spike test was described as the "headline improvement" for 2 workers in run 1 (p95=1,148ms, 0% errors). Run 2 shows p95=60,001ms and 9.16% errors — a complete regression to 1-worker-like behavior. **The spike test result is NOT reproducible** and cannot be used as a reliable thesis data point. The spike test's inherent noise (sudden 300 VU burst for only 30s) makes it sensitive to OS scheduler state, connection timing, and worker load distribution at the moment of the burst.

**Recovery test (R1: PASS, R2: FAIL):** Same pattern as spike — run 1 passed cleanly (p95=667ms, 0.60% errors), run 2 failed catastrophically (p95=60s, 5.44% errors). Recovery depends on the same burst dynamics as the spike test.

**Stress RPS (R1: 171, R2: 76):** The super-linear 5.9x scaling claim from run 1 (171 RPS vs 1w's 29) is NOT confirmed by run 2 (76 RPS). Run 2's 76 RPS vs 1w's 82 RPS suggests 2w may not provide throughput improvement under sustained stress — the benefit is in latency (p95=477ms) and error rate (1.71%). The run 1 RPS of 171 may have been an anomaly.

**Contention/Read-Write variance:** Contention booking p95 went from 76ms to 141ms; read/write went from 37/40ms to 55/74ms. These moderate-load tests showed more variance than expected, possibly due to background system activity.

### Conclusion on Stability
The 2-worker configuration is **reliable for moderate-load tests** (load, soak, endpoint benchmark). High-concurrency burst tests (spike, recovery) are **not reproducible** and should be interpreted as range indicators rather than precise values.

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Purpose:** Verify all endpoints are functional before heavy testing.

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 79ms* | 42ms |
| Avg | 123ms* | 19ms |
| Max | 10.1s* | 105ms |
| Error rate | 0% | 0% |
| Total requests | 1,499 | 2,829 |
| RPS | ~47 | ~90 |

*Run 1 had a single 10s network send delay inflating avg/max/p95. Server processing was unaffected (avg 17ms, p95 35ms). Run 2 shows the true baseline without anomalies: p95=42ms, max=105ms.

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

| Scenario | R1 p(95) | R2 p(95) | Threshold | Result |
|----------|----------|----------|-----------|--------|
| Light Reads | 68ms | 46ms | <200ms | PASS |
| List Reads | 51ms | 72ms | <500ms | PASS |
| Search & Filter | 58ms | 25ms | <500ms | PASS |
| Writes | 71ms | 42ms | <1000ms | PASS |
| Heavy Aggregations | 74ms | 44ms | <1500ms | PASS |

- **Total requests:** 25,470 (R1), 27,120 (R2)
- **Error rate:** 0% (both runs)
- **Total RPS:** ~55 (R1), ~59 (R2)

**All 5 scenarios passed in both runs.** Results are consistent — all well within thresholds.

**Conclusion:** Per-endpoint performance is excellent and reproducible at 20 VUs with 2 workers.

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

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 29ms | 32ms |
| Avg | 17ms | 18ms |
| Max | 155ms | 92ms |
| Error rate | 0% | 0% |
| Total requests | 15,431 | 15,374 |
| RPS | ~32 | ~32 |

**Comparison with 1 worker (Run 2 data):**

| Metric | 1w | 2w |
|--------|----|----|
| p(95) | 29ms | 32ms |
| Max | 72ms | 92ms |
| RPS | 32 | 32 |
| Error rate | 0% | 0% |

**Analysis:** Extremely consistent across runs (p95 29–32ms, 0% errors, 32 RPS). At 50 VUs, both 1w and 2w handle the load identically. The run 1 comparison that showed 1w max=10.3s vs 2w max=155ms reflected a 1w anomaly, not a real improvement from adding workers.

**Conclusion:** Normal production load is handled effortlessly by both configurations. Results are highly reproducible.

---

### B.2 Stress Test

**Purpose:** Progressive overload to find the degradation point.

**Config:** Ramp 0 → 50 (1 min) → 50 → 100 (2 min) → 100 → 200 (2 min) → 200 → 300 (2 min) → 300 → 0 (1 min). Total: ~8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 643ms | 477ms |
| p(90) | 495ms | — |
| Median (p50) | 87ms | — |
| Avg | 331ms | 1,255ms |
| Max | 60s | 60s |
| Error rate | 0.19% | 1.71% |
| Total requests | 82,027 | 38,509 |
| RPS | **171** | **76** |
| Bookings | 9,604 / 19 fail | — |
| Threshold | PASS | PASS |

**Comparison with 1 worker (using reliable Run 2 data):**

| Metric | 1w (R2) | 2w (R1) | 2w (R2) |
|--------|---------|---------|---------|
| p(95) | 457ms | 643ms | 477ms |
| RPS | 82 | 171 | 76 |
| Error rate | 1.48% | 0.19% | 1.71% |
| Max | 60s | 60s | 60s |

**Analysis — Run Variability:**

The stress test reveals significant run-to-run variability:

1. **RPS varied dramatically:** Run 1 showed 171 RPS (appearing to be 5.9x over 1w's 29 RPS). Run 2 shows 76 RPS, which is actually *below* 1w's run 2 RPS of 82. **The super-linear scaling claim from run 1 is NOT reproducible.**

2. **p(95) improved in run 2** (477ms vs 643ms), suggesting per-request latency may be slightly better, but total throughput dropped.

3. **Both runs PASS** the threshold (p95 < 1500ms), confirming the stress test is a reliable PASS for 2 workers.

4. **No stuck connections** in either run. Both completed in ~8 minutes as designed.

The high run-to-run RPS variance (171 vs 76) suggests the stress test's throughput is sensitive to OS-level scheduling decisions about how the 300 VU connections are distributed across the two workers. This makes stress RPS an unreliable comparison metric without more data points.

**Conclusion:** Two workers consistently PASS the stress test (p95 477–643ms, <2% errors). However, the throughput improvement over 1 worker is unclear — it ranges from negligible to 5.9x depending on the run. More runs are needed to establish a reliable throughput baseline.

---

### B.3 Spike Test

**Purpose:** Test system response to sudden traffic burst and recovery capability.

**Config:** 0 → 10 VUs (30s) → hold 10 (1 min) → spike 10 → 300 (10s) → hold 300 (30s) → drop 300 → 10 (10s) → hold 10 (1 min) → 0. Total stages: ~4 min.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 1,148ms | **60,001ms** |
| p(90) | 1,045ms | — |
| Median (p50) | 648ms | — |
| Avg | 570ms | 5,884ms |
| Max | 2,281ms | 60,030ms |
| Error rate | 0% | **9.16%** |
| Total requests | 12,134 | 2,785 |
| RPS | ~13 | ~12 |
| Threshold | **PASS** | **FAIL** |

**⚠ CRITICAL: This result is NOT reproducible.** Run 1 passed cleanly (p95=1,148ms, 0% errors). Run 2 failed catastrophically (p95=60s, 9.16% errors) — identical to 1-worker behavior.

**Comparison across runs and configurations:**

| Metric | 1w (both runs) | 2w Run 1 | 2w Run 2 |
|--------|---------------|----------|----------|
| p(95) | ~60s | 1,148ms | 60,001ms |
| Error rate | ~9% | 0% | 9.16% |
| Threshold | FAIL | PASS | FAIL |

**Analysis — Why the inconsistency:**

The spike test creates a 300 VU burst for only 30 seconds. The outcome depends on:

1. **Worker load distribution at burst time.** If the OS distributes connections evenly (150/150), both workers stay manageable. If one worker gets 200+ connections while the other gets fewer, the overloaded worker cascades exactly like a single worker.
2. **OS scheduler state.** At the microsecond level, the burst timing relative to the OS scheduler's process allocation decisions matters.
3. **Database connection pool state.** If one worker's pool is momentarily busier, the burst compounds the imbalance.

Run 1 hit a lucky distribution; run 2 did not. The spike test is inherently a **probabilistic test** for 2 workers — sometimes the load splits well, sometimes it doesn't. This is a critical architectural finding: **2 workers does not reliably survive 300 VU spikes.**

**Conclusion:** The spike test CANNOT be claimed as a reliable improvement for 2 workers. It passes in some runs and fails in others. For the thesis, this should be reported as "inconsistent — passes ~50% of runs" rather than a definitive PASS or FAIL. The 1-worker spike test is consistently FAIL, confirming the single event loop limitation is real.

---

### B.4 Soak Test

**Purpose:** Long-running stability test to detect memory leaks, connection pool exhaustion, or gradual latency creep.

**Config:** Ramp 0 → 30 VUs (1 min) → hold 30 VUs (30 min) → ramp down (1 min). Total: ~32 min.
**Thresholds:** p(95) < 700ms, error rate < 1%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 28ms | 31ms |
| Avg | 22ms | 17ms |
| Max | 10.3s* | 94ms |
| Error rate | 0.00% | 0.00% |
| Total requests | 43,775 | 43,958 |
| RPS | ~23 | ~23 |
| Bookings created | 5,190 | — |
| Duration | 32 min | 32 min |

*Run 1 had a single outlier (10.3s) in http_req_sending; not reproduced in run 2.

**Comparison with 1 worker (using run 2 data for both):**

| Metric | 1w | 2w |
|--------|----|----|
| p(95) | 25ms | 31ms |
| RPS | 23 | 23 |
| Error rate | 0% | 0% |

**Analysis:** With proper re-seeding (`run_tests.sh`), both 1w and 2w show **identical soak RPS of 23** and similar p(95) (25–31ms). The run 1 "3.3x RPS improvement" was an artifact of 1w's lower RPS in its first run (7 RPS, likely affected by lingering state). At 30 VUs, both configurations handle the load identically — the bottleneck is not the event loop at this concurrency level.

**Conclusion:** Rock-solid stability over 32 minutes in both runs. No resource leaks. The soak test is the most reproducible test in the suite. At 30 VUs, worker count makes no difference.

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

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| Booking latency p(95) | 76ms | 141ms |
| Booking latency avg | 32ms | 43ms |
| HTTP p(95) | — | 108ms |
| Max | 685ms | 1,023ms |
| Error rate | 0.00% | 0.00% |
| Total requests | 15,022 | 16,358 |
| RPS | ~122 | ~135 |
| Bookings success | 283 | 283 |
| Sold out (409) | 7,227 | — |

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

| Metric | R1 Read | R1 Write | R2 Read | R2 Write |
|--------|---------|----------|---------|----------|
| p(95) | 37ms | 40ms | 55ms | 74ms |
| Avg | 21ms | 26ms | — | — |
| Error rate | 0% | 0% | 0% | 0% |

- **Combined RPS:** ~27 (R1), ~43 (R2)
- **Checks passed:** 100% (both runs)

**Analysis:**

Run-to-run variance is higher than expected for this moderate-load test:

| Metric | R1 Read | R2 Read | R1 Write | R2 Write |
|--------|---------|---------|----------|----------|
| p(95) | 37ms | 55ms | 40ms | 74ms |

Both runs pass all thresholds with 0% errors, but absolute p(95) values vary by ~50%. This suggests sensitivity to background system activity or Docker resource scheduling. The RPS difference (27 vs 43) is significant and may reflect methodology improvements in run 2.

**Conclusion:** Both runs confirm 0% errors and pass all thresholds at 30 VUs. The write penalty (write/read ratio) is consistent: ~1.08x (R1) and ~1.35x (R2). Two workers handle mixed traffic reliably.

---

### C.3 Recovery Test

**Purpose:** Measure time-to-recovery after sudden overload. Unlike the spike test (which focuses on behavior during the spike), this test has a long post-spike observation window.

**Config:** 1 min baseline (30 VUs) → 10s spike to 300 VUs → 30s hold at 300 → 10s drop to 30 → 4 min observation (30 VUs) → 20s ramp down. Total: ~6 min.
**Thresholds:** p(95) < 10,000ms, error rate < 30%, checks > 70%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 667ms | **59,996ms** |
| Avg | 590ms | 3,877ms |
| Max | 60s | 60s |
| Error rate | 0.60% | **5.44%** |
| Total requests | 21,058 | 5,721 |
| RPS | ~57 | ~15 |
| Threshold | **PASS** | **FAIL** |

**⚠ CRITICAL: This result is NOT reproducible.** Same pattern as the spike test — run 1 passed, run 2 failed catastrophically.

**Analysis:**

1. **Run 1:** The system recovered from the 300 VU spike. Error rate was minimal (0.60%), and the API returned to normal during the 4-minute observation window.

2. **Run 2:** The system did NOT recover. p(95) hit 60s timeout, requests dropped to 5,721 (vs 21,058 in run 1), and error rate jumped to 5.44%. The system entered the same timeout cascade seen in 1-worker spike tests.

3. **The recovery test depends on the same burst dynamics as the spike test.** If the spike overwhelms one worker (uneven distribution), the system enters cascade failure and cannot recover within the observation window.

**Conclusion:** The recovery test is inconsistent for 2 workers, mirroring the spike test variability. The system sometimes recovers (run 1) and sometimes does not (run 2). This confirms that 2 workers is on the edge of surviving 300 VU bursts.

---

## System Behavior Under Failure

### Observed Failure Patterns (Multi-Run)

| Test | Peak VUs | Run 1 | Run 2 | Consistent? |
|------|----------|-------|-------|-------------|
| Load (50 VUs) | 50 | Healthy | Healthy | Yes |
| Stress (300 VUs) | 300 | Self-recovered | Self-recovered | Yes |
| Spike (300 VUs) | 300 | Self-recovered | **Unresponsive** | **No** |
| Breakpoint (500 VUs) | 500 | Required restart | Required restart | Yes |
| Soak (30 VUs) | 30 | Healthy | Healthy | Yes |
| Recovery (300 VU spike) | 300 | Self-recovered | **Timeout cascade** | **No** |

### Key Finding: Burst Resilience is Probabilistic

With 2 workers, 300 VU bursts sometimes succeed and sometimes fail. The outcome depends on how the OS distributes connections across the two workers at the moment of the burst. This is fundamentally different from 1 worker (always fails at 300 VU burst) but not yet reliable.

### Root Cause

Two Uvicorn workers run two independent Python asyncio event loops. When concurrent connections spike:

1. **Load distribution** — the OS distributes incoming connections across both workers
2. **Independent failure domains** — if one worker's event loop becomes saturated, the other can still process requests
3. **Doubled connection capacity** — each worker handles its own connection queue, effectively doubling the total concurrent connection capacity
4. **No shared state** — workers don't share the event loop, so one worker's backlog doesn't affect the other

The bottleneck is still concurrency (not CPU), but two event loops provide enough capacity to survive 300 VU spikes that overwhelm a single worker.

---

## 1 Worker vs 2 Worker Comparison (Multi-Run)

### Summary (using most reliable run for each metric)

| Metric | 1w | 2w | Reproducible? |
|--------|----|----|---------------|
| Load p(95) | 29ms | 32ms | Yes (nearly identical) |
| Load max | 72ms | 92ms | Yes |
| Stress p(95) | 457ms | 477ms | Yes (both PASS) |
| Stress RPS | 82 | 76–171 | **No** (high variance) |
| Spike result | FAIL | **INCONSISTENT** | No (R1 PASS, R2 FAIL) |
| Soak p(95) | 25ms | 31ms | Yes |
| Soak RPS | 23 | 23 | Yes (identical) |
| Breakpoint | FAIL | FAIL | Yes |
| Contention p(95) | 42–48ms | 76–141ms | Yes (2w always worse) |

### Where 2 Workers Reliably Helps

1. **Stress test consistency** — both runs PASS (p95 477–643ms vs threshold of 1500ms). 1w also passes but with similar p95.
2. **Correct concurrency control** — `with_for_update()` works correctly across both workers in all runs.
3. **No stuck connections** — the 1w run 1 stuck connection (20+ minutes) was not seen in any 2w run.

### Where 2 Workers Does NOT Reliably Help

1. **Spike resilience** — inconsistent (PASS in run 1, FAIL in run 2). NOT a reliable improvement.
2. **Recovery capability** — inconsistent (same pattern as spike).
3. **Stress RPS** — the "5.9x super-linear scaling" from run 1 was NOT reproduced. Run 2 shows 76 RPS vs 1w's 82 RPS.

### Where 2 Workers Hurts

1. **Contention latency** — booking p95 consistently higher (76–141ms vs 42–48ms for 1w).
2. **Low-load overhead** — baseline p95 ~42ms vs 1w's ~45ms (similar, not significant after removing run 1 outlier).

### Revised Scaling Assessment

| Metric | Run 1 Scaling | Run 2 Scaling | Reliable? |
|--------|--------------|--------------|-----------|
| Stress RPS | 5.9x | 0.9x | **No** |
| Soak RPS | 3.3x | 1.0x | **No** (methodology artifact) |
| Spike survival | 0→100% | 0→0% | **No** |

**The run 1 scaling claims were largely artifacts** of 1w anomalies (stuck connection, low soak RPS from poor re-seeding). With proper methodology (run 2), 2 workers shows **marginal improvement** over 1 worker for most metrics. The primary reliable difference is contention (worse) and the elimination of stuck connections.

---

## Key Conclusions — 2 Uvicorn Workers (Multi-Run)

### Performance Envelope

| Metric | Value | Reproducible? |
|--------|-------|---------------|
| Comfortable capacity | 50 VUs / 32 RPS, p(95) ~30ms | Yes |
| Stress capacity | 300 VUs, p(95) ~500ms, PASS | Yes |
| Spike survival | 300 VUs sudden | **No** (inconsistent) |
| Collapse point | 500 VUs sustained (breakpoint FAIL) | Yes |

### Architectural Strengths (confirmed across runs)
1. **Reliable stress handling** — consistently PASS at 300 VUs with <2% errors
2. **No stuck connections** — max latency capped at 60s timeout, no 20+ minute hangs
3. **Correct concurrency control** — `with_for_update()` works correctly across both workers
4. **Stable moderate-load performance** — load, soak, and endpoint benchmark are highly reproducible

### Architectural Weaknesses (confirmed across runs)
1. **Increased database contention** — booking latency 76–141ms vs 1w's 42–48ms
2. **Unreliable burst resilience** — 300 VU spike test is probabilistic, not guaranteed
3. **Breakpoint still fails** — 2 event loops insufficient for open-model 500 iter/s load
4. **Marginal throughput improvement** — stress RPS not reliably better than 1 worker

### Implications for 4-Worker Test
The key question for 4 workers: does adding more failure domains make spike/recovery results more consistent? Or does the CPU-to-worker ratio (4 workers on 2 CPUs) create new problems?
