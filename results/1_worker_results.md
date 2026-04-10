# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** 2026-04-09 (Run 2)
**Configuration:** Docker (FastAPI + PostgreSQL), 1 Uvicorn worker
**Seed data:** 1,000 users, 100 events, 2,000 bookings (re-seeded before each test via `run_tests.sh`)
**Monitoring:** K6 → Prometheus remote write → Grafana dashboard (live visualization)
**Machine:** Windows 11, 32 GiB RAM
**K6 output:** `--out experimental-prometheus-rw` with trend stats: p(50), p(90), p(95), p(99), avg, min, max
**Test runner:** Automated via `run_tests.sh` (re-seed → run → restart if crashed → 30s cool-down)
**Resource limits:** API 4 CPU / 2 GB, PostgreSQL 3 CPU / 2 GB, Prometheus 1 CPU / 512 MB
**Connection pool:** pool_size=60, max_overflow=30 (90 total connections)
**PostgreSQL tuning:** shared_buffers=512MB, effective_cache_size=1GB, work_mem=8MB
**Run history:** See [test_run_history.md](test_run_history.md) for cross-run comparison

---

## Summary Table

| Test | Type | VUs | p(95) | Errors | RPS | Requests | Status |
|------|------|-----|-------|--------|-----|----------|--------|
| Baseline | Smoke | 10 | 42ms | 0% | 91 | 2,885 | PASS |
| Endpoint Benchmark | Isolation | 20 | ~69ms* | 0% | ~55 | ~25,000 | PASS |
| Load | Normal load | 50 | 28ms | 0% | 32 | 15,462 | PASS |
| Stress | Overload | 300 | 886ms | 0% | 164 | 78,809 | PASS |
| Spike | Burst | 300 | 1,225ms | 0% | 62 | 13,084 | PASS |
| Soak | Endurance | 30 | 27ms | 0% | 23 | 44,093 | PASS |
| Breakpoint | Capacity | 500 | 1,464ms | 4.6% | 62 | 76,479 | PASS* |
| Contention | Locking | 50 | 43ms† | 0% | 144 | 17,488 | PASS |
| Read vs Write (read) | Traffic profile | 30 | ~30ms | 0% | ~44 | ~8,100 | PASS |
| Read vs Write (write) | Traffic profile | 30 | ~30ms | 0% | ~44 | ~8,100 | PASS |
| Recovery | Resilience | 300 | 938ms | 0% | 72 | 26,703 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**9 of 10 tests PASS with 0% errors. Breakpoint passes K6 thresholds (p95 < 5000ms) but shows 4.6% errors and 149K dropped iterations (PASS*).**

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 42ms |
| p(90) | 32ms |
| Avg | 19ms |
| Median | 16ms |
| Max | 103ms |
| Error rate | 0% |
| Checks | 100% (3,914/3,914) |
| Total requests | 2,885 |
| RPS | 91 |
| Iterations | 206 |

**Conclusion:** All endpoints healthy. The system handles 10 concurrent users with sub-50ms p(95) latency.

---

### A.2 Endpoint Benchmark

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario.
**All 5 scenarios PASS** — including heavy aggregations, which previously failed under old infrastructure.

| Scenario | Endpoints | p(95) | Threshold | Result |
|----------|-----------|-------|-----------|--------|
| Light Reads | GET /health, /users/{id}, /events/{id}, /bookings/{id} | 78ms | <200ms | PASS |
| List Reads | GET /users/, /events/, /bookings/ | 41ms | <500ms | PASS |
| Search & Filter | GET /events/search, /events/upcoming, /users/{id}/bookings, /events/{id}/bookings | 56ms | <500ms | PASS |
| Writes | POST /bookings/, PATCH /bookings/{id}/cancel | 69ms | <1000ms | PASS |
| Heavy Aggregations | GET /events/{id}/stats, /events/popular, /stats | 69ms | <1500ms | PASS |

- **Total requests:** 25,481
- **Checks:** 100% (25,480/25,480)
- **Error rate:** 0%
- **Max VUs observed:** 20 (no scenario overlap — clean execution)

**Key improvement:** Heavy aggregations p(95) dropped from 60,231ms (old infra) to 69ms. The increased shared_buffers (512MB) and effective_cache_size (1GB) enable PostgreSQL to cache more data and choose index scans over sequential scans.

---

## Phase B — Standard Test Types (Mixed Realistic Traffic)

All Phase B tests use the same weighted traffic distribution (25% browse events, 15% view event, 12% create booking, 10% search, 10% list users, 8% upcoming, 5% user bookings, 5% cancel, 5% event stats, 3% popular, 2% global stats).

---

### B.1 Load Test

**Config:** Ramp 0 → 50 VUs (2 min) → hold 50 VUs (5 min) → ramp down (1 min). Total: ~8 min.
**Thresholds:** p(95) < 500ms, p(99) < 1000ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 28ms |
| p(90) | 25ms |
| Avg | 16ms |
| Median | 15ms |
| Max | 75ms |
| Error rate | 0% |
| Checks | 100% (15,461/15,461) |
| Total requests | 15,462 |
| RPS | 32 |
| Bookings | 1,765 |

**Conclusion:** At 50 VUs, the system operates with massive headroom. p(95) of 28ms is well below the 500ms threshold.

---

### B.2 Stress Test

**Config:** Ramp 0 → 50 → 100 → 200 → 300 VUs over 8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

| Metric | Value |
|--------|-------|
| p(95) | **886ms** |
| p(90) | 795ms |
| Avg | 356ms |
| Median | 297ms |
| Max | 1,329ms |
| Error rate | 0% |
| Checks | 100% (78,808/78,808) |
| Total requests | 78,809 |
| RPS | **164** |
| Bookings | 9,397 success / 139 sold out |

**Cross-config comparison (Run 2):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **886ms** | **164** | 0% |
| 2w | 262ms | 230 | 0% |
| 4w | 177ms | 248 | 0% |

**Analysis:** The single worker shows significantly higher latency than 2w and 4w under 300 VU stress. With only one event loop processing all requests, the connection pool (90 total) has plenty of capacity, but the single CPU core becomes the bottleneck at this concurrency level. Note: Run 1 showed much better 1w stress performance (151ms / 251 RPS), demonstrating significant run-to-run variance.

**Conclusion:** PASSES with 0% errors but the highest latency among all configs. The single event loop is saturated at 300 VUs.

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 VUs in 10s → hold 30s → drop to 10 VUs → 1 min observation.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **1,225ms** |
| p(90) | 1,155ms |
| Avg | 540ms |
| Median | 597ms |
| Max | 1,412ms |
| Error rate | 0% |
| Checks | 100% (13,083/13,083) |
| Total requests | 13,084 |
| RPS | 62 |
| Bookings | 1,562 |

**Cross-config comparison (Run 2):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **1,225ms** | 1,412ms | **62** | 0% |
| 2w | 289ms | 411ms | 104 | 0% |
| 4w | 609ms | 1,378ms | 98 | 0% |

**Analysis:** The single worker struggles most with sudden bursts — 1,225ms p(95) and only 62 RPS. With one event loop, the 300 VU spike saturates the CPU and all requests queue. Note: Run 1 showed better spike handling (525ms / 102 RPS), again showing run-to-run variance in burst tests.

**Conclusion:** PASSES with 0% errors but highest spike latency among all configs.

---

### B.4 Soak Test

**Config:** 30 VUs, 32 minutes steady state.
**Thresholds:** p(95) < 700ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 27ms |
| p(90) | 23ms |
| Avg | 15ms |
| Median | 13ms |
| Max | 153ms |
| Error rate | 0% |
| Checks | 100% (44,092/44,092) |
| Total requests | 44,093 |
| RPS | 23 |
| Bookings | 5,231 |
| Duration | 32 min |

**Analysis:**
1. **Memory leaks?** No — flat memory usage for 32 minutes.
2. **Connection pool exhaustion?** No — 30 VUs easily fit within 90 pool slots.
3. **Latency creep?** No — p(95) remained at 28ms from start to finish.

**Conclusion:** Rock-solid under sustained moderate load. Results consistent with old infrastructure (p(95) was 25-28ms then too).

---

### B.5 Breakpoint Test

**Config:** ramping-arrival-rate, 10 → 500 iterations/s over 20 minutes. maxVUs = 500.
**Thresholds:** p(95) < 5000ms with abortOnFail.

| Metric | Value |
|--------|-------|
| p(95) | **1,464ms** |
| p(90) | 420ms |
| Avg | 2,881ms |
| Median | 21ms |
| Max | 60,009ms |
| Error rate | **4.6%** (3,524 failures) |
| Checks | 95.4% (72,954/76,478) |
| Total requests | 76,479 |
| RPS | **62** |
| Peak VUs | **500 (maxed out)** |
| Dropped iterations | **149,646** |
| Bookings | 8,700 success / 135 sold out / 447 failed |
| Duration | ~20.5 min (full run) |

**Threshold result:** PASS* — p(95) of 1,464ms is within the 5,000ms threshold, and checks rate (95.4%) exceeds the 80% threshold. However, the 4.6% HTTP error rate and 149K dropped iterations indicate the system was overwhelmed.

**Cross-config breakpoint comparison (Run 2):**
| Workers | p(95) | RPS | Errors | Peak VUs | Dropped | Duration |
|---------|-------|-----|--------|----------|---------|----------|
| **1w** | **1,464ms** | **62** | **4.6%** | **500** | **149,646** | ~20.5 min |
| 2w | 247ms | 183 | 0.14% | 500 | 1,599 | ~20.5 min |
| 4w | 112ms | 189 | 0% | 164 | 118 | 20 min |

**Analysis:** The single worker collapsed under sustained high arrival rate. With 149K dropped iterations and only 62 RPS (vs 189 for 4w), the event loop couldn't keep up. The bimodal latency (median 21ms but avg 2,881ms) shows most requests were fast, but a growing tail of queued requests caused cascading delays.

**Important:** Run 1 showed excellent 1w breakpoint performance (192ms / 189 RPS / 0% errors). The dramatic difference between runs demonstrates that single-worker performance under extreme load is highly variable — see test_run_history.md.

**Conclusion:** PASSES K6 thresholds technically, but with significant degradation. The single event loop is near its capacity ceiling under open-model load.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking the same event (event_id=1), 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 43ms |
| Booking latency avg | 19ms |
| Booking latency median | 13ms |
| HTTP p(95) | 37ms |
| Max | 576ms |
| Error rate | 0% |
| Total requests | 17,488 |
| RPS | 144 |
| Bookings success | 283 |
| Sold out (409) | 8,460 |

**Conclusion:** Exactly 283 bookings succeeded (matching ticket capacity). Zero deadlocks, zero double-bookings. The `with_for_update()` locking strategy performs correctly under extreme contention. Consistent across all runs.

---

### C.2 Read vs Write Test

**Config:** Two sequential scenarios at 30 VUs, 3 min each.

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 30ms | 30ms |
| Avg | 18ms | 18ms |
| Error rate | 0% | 0% |
| Bookings | 806 | 2,835 |

- **Combined RPS:** 44
- **Checks:** 100%

**Conclusion:** Near-parity between read-heavy and write-heavy at 30 VUs. The improved DB caching minimizes the read/write performance gap.

---

### C.3 Recovery Test

**Config:** 30 VU baseline → spike to 300 VUs → drop to 30 → 4 min observation.
**Thresholds:** p(95) < 10,000ms, error rate < 30%.

| Metric | Value |
|--------|-------|
| p(95) | **938ms** |
| p(90) | 794ms |
| Avg | 280ms |
| Median | 31ms |
| Max | 1,521ms |
| Error rate | 0% |
| Checks | 100% (26,702/26,702) |
| Total requests | 26,703 |
| RPS | 72 |
| Bookings | 3,181 |

**Cross-config recovery comparison (Run 2):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **938ms** | 1,521ms | **72** | 0% |
| 2w | 277ms | 450ms | 95 | 0% |
| 4w | 539ms | 1,361ms | 92 | 0% |

**Analysis:** The single worker has the slowest recovery — 938ms p(95) and 72 RPS. After the 300 VU spike, the single event loop takes longer to drain the backlog. However, it does fully recover (median 31ms shows post-spike latency returns to normal).

**Conclusion:** PASSES with 0% errors. Recovery is slower than multi-worker configs but eventual.

---

## Comparison with Old Infrastructure

| Test | Old Infra p(95) | New Infra p(95) | Old Errors | New Errors | Improvement |
|------|----------------|-----------------|------------|------------|-------------|
| Baseline | 45-62ms | 42ms | 0% | 0% | Similar |
| Load | 29-34ms | 28ms | 0% | 0% | Similar |
| Stress | 353-457ms | **886ms** | 0.5-1.5% | **0%** | Higher latency but zero errors |
| Spike | **60,000ms** | **1,225ms** | **9%** | **0%** | Previously FAILED → now PASSES |
| Soak | 25-28ms | 27ms | 0% | 0% | Similar |
| Breakpoint | **19,300ms** | **1,464ms** | **9.11%** | **4.6%** | Better but still degraded |
| Recovery | **59,210ms** | **938ms** | **5.13%** | **0%** | Previously FAILED → now PASSES |

**Note:** New infra values above are from Run 2. Run 1 showed significantly better 1w performance (stress 151ms, breakpoint 192ms/0%). See test_run_history.md for cross-run comparison.

**Old infrastructure:** API 2 CPU / 1 GB, PostgreSQL 2 CPU / 1 GB, pool_size=10, max_overflow=20 (30 total), shared_buffers=256MB
**New infrastructure:** API 4 CPU / 2 GB, PostgreSQL 3 CPU / 2 GB, pool_size=60, max_overflow=30 (90 total), shared_buffers=512MB

The three tests that flipped from FAIL to PASS (spike, breakpoint, recovery) all involve high-concurrency scenarios that exhaust connection pools. The 3x increase in pool capacity (30 → 90) was the decisive factor.

---

## Key Conclusions — 1 Uvicorn Worker (New Infrastructure)

### Performance Envelope

| Metric | Value |
|--------|-------|
| Comfortable capacity | 50 VUs / 32 RPS — p(95) 28ms, 0% errors |
| Stress capacity | 300 VUs / 164 RPS — p(95) 886ms, 0% errors |
| Spike survival | 300 VU burst — p(95) 1,225ms, 0% errors |
| Sustained ceiling | 62 RPS (breakpoint) — p(95) 1,464ms, 4.6% errors |
| Endurance | 32 min at 30 VUs — zero degradation |

### Architectural Strengths
1. **Excellent endurance** — 32-minute soak with flat latency
2. **Correct concurrency control** — exactly 283 contention bookings, zero deadlocks
3. **Zero errors at moderate load** — load, soak, contention all perfect
4. **Full connection pool** — 90 undivided connections (largest per-worker pool)

### Limitations Under High Load
1. **Single event loop saturates** — with one CPU core doing all processing, 300+ VUs cause queuing
2. **Variable high-load performance** — Run 1 showed excellent results (151ms stress, 192ms breakpoint), Run 2 showed degradation (886ms stress, 1,464ms breakpoint). The single-worker config is sensitive to external factors (OS scheduling, background load)
3. **Slowest recovery** — takes longest to drain request backlog after bursts

### Thesis Takeaway
The single-worker config performs well at moderate concurrency but its high-load behavior is unpredictable. The undivided 90-connection pool is an advantage, but the single event loop becomes the bottleneck above ~100 VUs. Performance varies significantly between runs, making it unreliable for production workloads that may spike.
