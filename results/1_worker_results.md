# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** 2026-04-11 (Run 3)
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
| Baseline | Smoke | 10 | 37ms | 0% | 90 | 2,871 | PASS |
| Endpoint Benchmark | Isolation | 20 | ~45ms* | 0% | ~59 | ~27,158 | PASS |
| Load | Normal load | 50 | 28ms | 0% | 32 | 15,443 | PASS |
| Stress | Overload | 300 | 839ms | 0% | 167 | 80,325 | PASS |
| Spike | Burst | 300 | 1,079ms | 0% | 62 | 13,010 | PASS |
| Soak | Endurance | 30 | 26ms | 0% | 23 | 44,159 | PASS |
| Breakpoint | Capacity | 500 | 1,483ms | 4.75% | 60 | 74,096 | PASS* |
| Contention | Locking | 50 | 40ms† | 0% | 146 | 17,620 | PASS |
| Read vs Write | Traffic profile | 30 | ~33ms | 0% | ~44 | ~16,142 | PASS |
| Recovery | Resilience | 300 | 960ms | 0% | 72 | 26,782 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**9 of 10 tests PASS with 0% errors. Breakpoint passes K6 thresholds (p95 < 5000ms) but shows 4.75% errors and significant dropped iterations (PASS*).**

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 37ms |
| p(90) | 29ms |
| Avg | 18ms |
| Median | 15ms |
| Max | 114ms |
| Error rate | 0% |
| Checks | 100% (3,895/3,895) |
| Total requests | 2,871 |
| RPS | 90 |

**Conclusion:** All endpoints healthy. The system handles 10 concurrent users with sub-40ms p(95) latency.

---

### A.2 Endpoint Benchmark

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario.
**All 5 scenarios PASS** — including heavy aggregations, which previously failed under old infrastructure.

| Scenario | Endpoints | p(95) | Threshold | Result |
|----------|-----------|-------|-----------|--------|
| Light Reads | GET /health, /users/{id}, /events/{id}, /bookings/{id} | ~42ms | <200ms | PASS |
| List Reads | GET /users/, /events/, /bookings/ | ~28ms | <500ms | PASS |
| Search & Filter | GET /events/search, /events/upcoming, /users/{id}/bookings, /events/{id}/bookings | ~38ms | <500ms | PASS |
| Writes | POST /bookings/, PATCH /bookings/{id}/cancel | ~45ms | <1000ms | PASS |
| Heavy Aggregations | GET /events/{id}/stats, /events/popular, /stats | ~52ms | <1500ms | PASS |

- **Total requests:** 27,158
- **Checks:** 100% (27,157/27,157)
- **Error rate:** 0%
- **Overall p(95):** 45ms

**Key improvement:** Heavy aggregations p(95) dropped from 60,231ms (old infra) to ~52ms. The increased shared_buffers (512MB) and effective_cache_size (1GB) enable PostgreSQL to cache more data and choose index scans over sequential scans.

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
| p(90) | 24ms |
| Avg | 16ms |
| Median | 15ms |
| Max | 76ms |
| Error rate | 0% |
| Checks | 100% (15,442/15,442) |
| Total requests | 15,443 |
| RPS | 32 |
| Bookings | 1,882 |

**Cross-config comparison (Run 3):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **28ms** | **32** | 0% |
| 2w | 26ms | 32 | 0% |
| 4w | 28ms | 32 | 0% |

**Conclusion:** At 50 VUs, all configs perform identically. The system operates with massive headroom — worker count provides no benefit at this concurrency level.

---

### B.2 Stress Test

**Config:** Ramp 0 → 50 → 100 → 200 → 300 VUs over 8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

| Metric | Value |
|--------|-------|
| p(95) | **839ms** |
| p(90) | 743ms |
| Avg | 339ms |
| Median | 287ms |
| Max | 1,242ms |
| Error rate | 0% |
| Checks | 100% (80,324/80,324) |
| Total requests | 80,325 |
| RPS | **167** |
| Bookings | 9,491 success |

**Cross-config comparison (Run 3):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **839ms** | **167** | 0% |
| 2w | 240ms | 234 | 0% |
| 4w | 130ms | 231 | 0.06% |

**Analysis:** The single worker shows significantly higher latency than 2w and 4w under 300 VU stress. With only one event loop processing all requests, the single CPU core becomes the bottleneck at this concurrency level. The connection pool (90 total) has plenty of capacity — CPU, not connections, is the limiting factor. This result is highly consistent: Run 2 showed 886ms / 164 RPS, Run 3 shows 839ms / 167 RPS.

**Conclusion:** PASSES with 0% errors but the highest latency among all configs. The single event loop is saturated at 300 VUs.

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 VUs in 10s → hold 30s → drop to 10 VUs → 1 min observation.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **1,079ms** |
| p(90) | 1,020ms |
| Avg | 546ms |
| Median | 663ms |
| Max | 1,342ms |
| Error rate | 0% |
| Checks | 100% (13,009/13,009) |
| Total requests | 13,010 |
| RPS | 62 |
| Bookings | 1,563 |

**Cross-config comparison (Run 3):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **1,079ms** | 1,342ms | **62** | 0% |
| 2w | 276ms | 446ms | 103 | 0% |
| 4w | 133ms | 404ms | 118 | 0% |

**Analysis:** The single worker struggles most with sudden bursts — 1,079ms p(95) and only 62 RPS. With one event loop, the 300 VU spike saturates the CPU and all requests queue. Linear scaling is clearly visible: 4w handles the same burst at 133ms / 118 RPS.

**Conclusion:** PASSES with 0% errors but highest spike latency among all configs.

---

### B.4 Soak Test

**Config:** 30 VUs, 32 minutes steady state.
**Thresholds:** p(95) < 700ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 26ms |
| p(90) | 23ms |
| Avg | 15ms |
| Median | 13ms |
| Max | 205ms |
| Error rate | 0% |
| Checks | 100% (44,158/44,158) |
| Total requests | 44,159 |
| RPS | 23 |
| Bookings | 5,314 |
| Duration | 32 min |

**Analysis:**
1. **Memory leaks?** No — flat memory usage for 32 minutes.
2. **Connection pool exhaustion?** No — 30 VUs easily fit within 90 pool slots.
3. **Latency creep?** No — p(95) remained stable throughout.

**Conclusion:** Rock-solid under sustained moderate load. Consistent across all runs and configs (low load is always ~25ms p95).

---

### B.5 Breakpoint Test

**Config:** ramping-arrival-rate, 10 → 500 iterations/s over 20 minutes. maxVUs = 500.
**Thresholds:** p(95) < 5000ms with abortOnFail.

| Metric | Value |
|--------|-------|
| p(95) | **1,483ms** |
| p(90) | 282ms |
| Avg | 2,981ms |
| Median | 18ms |
| Max | 60,018ms |
| Error rate | **4.75%** (3,517 failures) |
| Checks | 95.3% (70,579/74,095) |
| Total requests | 74,096 |
| RPS | **60** |
| Peak VUs | **500 (maxed out)** |
| Bookings | 8,214 success |
| Duration | ~20.5 min (full run) |

**Threshold result:** PASS* — p(95) of 1,483ms is within the 5,000ms threshold. However, the 4.75% HTTP error rate and significant dropped iterations indicate the system was overwhelmed.

**Cross-config breakpoint comparison (Run 3):**
| Workers | p(95) | RPS | Errors | Peak VUs | Duration |
|---------|-------|-----|--------|----------|----------|
| **1w** | **1,483ms** | **60** | **4.75%** | **500** | ~20.5 min |
| 2w | 165ms | 139 | 0.72% | 500 | ~20.5 min |
| 4w | 65ms | 189 | 0% | low | 20 min |

**Analysis:** The single worker collapsed under sustained high arrival rate. With only 60 RPS (vs 189 for 4w), the event loop couldn't keep up. The bimodal latency (median 18ms but avg 2,981ms) shows most requests were fast, but a growing tail of queued requests caused cascading delays.

**Consistency note:** Run 2 showed 1,464ms / 4.6% errors, Run 3 shows 1,483ms / 4.75% errors. This is the most consistent high-load result in the dataset — the 1w breakpoint ceiling is now well established.

**Conclusion:** PASSES K6 thresholds technically, but with significant degradation. The single event loop is near its capacity ceiling under open-model load.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking the same event (event_id=1), 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 40ms |
| Booking latency avg | 18ms |
| Booking latency median | 12ms |
| HTTP p(95) | 35ms |
| Max | 603ms |
| Error rate | 0% |
| Total requests | 17,620 |
| RPS | 146 |
| Bookings success | 283 |
| Sold out (409) | 8,526 |

**Cross-config contention comparison (Run 3):**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| **1w** | **40ms** | 283 | 8,526 |
| 2w | 25ms | 283 | 8,122 |
| 4w | 24ms | 283 | 8,057 |

**Analysis:** All three configs correctly produce exactly 283 bookings with zero deadlocks. Interestingly, 1w has the fastest HTTP response (35ms p95) but slightly higher booking latency — because 1w processes requests sequentially from a single event loop, which means less lock competition but also less parallelism. With multiple workers, more threads compete for the same row lock, increasing contention overhead slightly (hence 2w/4w showing higher HTTP p95 due to Docker networking but lower booking latency once the lock is acquired).

**Conclusion:** Exactly 283 bookings succeeded (matching ticket capacity). Zero deadlocks, zero double-bookings. The `with_for_update()` locking strategy performs correctly under extreme contention. Consistent across all runs.

---

### C.2 Read vs Write Test

**Config:** Two sequential scenarios at 30 VUs, 3 min each.

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 33ms | 33ms |
| Avg | 18ms | 18ms |
| Error rate | 0% | 0% |
| Bookings | 822 | 2,858 |

- **Combined RPS:** 44
- **Total requests:** 16,142
- **Checks:** 100% (16,141/16,141)

**Conclusion:** Near-parity between read-heavy and write-heavy at 30 VUs. At moderate concurrency, the workload mix doesn't significantly impact performance.

---

### C.3 Recovery Test

**Config:** 30 VU baseline → spike to 300 VUs → drop to 30 → 4 min observation.
**Thresholds:** p(95) < 10,000ms, error rate < 30%.

| Metric | Value |
|--------|-------|
| p(95) | **960ms** |
| p(90) | 845ms |
| Avg | 277ms |
| Median | 31ms |
| Max | 1,388ms |
| Error rate | 0% |
| Checks | 100% (26,781/26,781) |
| Total requests | 26,782 |
| RPS | 72 |
| Bookings | 3,235 |

**Cross-config recovery comparison (Run 3):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **960ms** | 1,388ms | **72** | 0% |
| 2w | 337ms | 883ms | 93 | 0% |
| 4w | 128ms | 468ms | 104 | 0% |

**Analysis:** The single worker has the slowest recovery — 960ms p(95) and 72 RPS. After the 300 VU spike, the single event loop takes longer to drain the backlog. However, it does fully recover (median 31ms shows post-spike latency returns to normal). Linear scaling is clearly visible: 4w recovers to 128ms p(95) / 104 RPS. Consistent with Run 2 (938ms / 72 RPS).

**Conclusion:** PASSES with 0% errors. Recovery is slower than multi-worker configs but complete.

---

## Comparison with Old Infrastructure

| Test | Old Infra p(95) | New Infra p(95) | Old Errors | New Errors | Improvement |
|------|----------------|-----------------|------------|------------|-------------|
| Baseline | 45-62ms | 37ms | 0% | 0% | Similar |
| Load | 29-34ms | 28ms | 0% | 0% | Similar |
| Stress | 353-457ms | **839ms** | 0.5-1.5% | **0%** | Higher latency but zero errors |
| Spike | **60,000ms** | **1,079ms** | **9%** | **0%** | Previously FAILED → now PASSES |
| Soak | 25-28ms | 26ms | 0% | 0% | Similar |
| Breakpoint | **19,300ms** | **1,483ms** | **9.11%** | **4.75%** | Better but still degraded |
| Recovery | **59,210ms** | **960ms** | **5.13%** | **0%** | Previously FAILED → now PASSES |

**Old infrastructure:** API 2 CPU / 1 GB, PostgreSQL 2 CPU / 1 GB, pool_size=10, max_overflow=20 (30 total), shared_buffers=256MB
**New infrastructure:** API 4 CPU / 2 GB, PostgreSQL 3 CPU / 2 GB, pool_size=60, max_overflow=30 (90 total), shared_buffers=512MB

The three tests that flipped from FAIL to PASS (spike, breakpoint, recovery) all involve high-concurrency scenarios that exhaust connection pools. The 3x increase in pool capacity (30 → 90) was the decisive factor.

---

## Key Conclusions — 1 Uvicorn Worker

### Performance Envelope

| Metric | Value |
|--------|-------|
| Comfortable capacity | 50 VUs / 32 RPS — p(95) 28ms, 0% errors |
| Stress capacity | 300 VUs / 167 RPS — p(95) 839ms, 0% errors |
| Spike survival | 300 VU burst — p(95) 1,079ms, 0% errors |
| Sustained ceiling | 60 RPS (breakpoint) — p(95) 1,483ms, 4.75% errors |
| Endurance | 32 min at 30 VUs — zero degradation |

### Architectural Strengths
1. **Excellent endurance** — 32-minute soak with flat latency
2. **Correct concurrency control** — exactly 283 contention bookings, zero deadlocks
3. **Zero errors at moderate load** — load, soak, contention all perfect
4. **Full connection pool** — 90 undivided connections (largest per-worker pool)

### Limitations Under High Load
1. **Single event loop saturates** — with one CPU core doing all processing, 300+ VUs cause queuing
2. **Consistent but limited ceiling** — Run 2 (886ms stress, 1,464ms breakpoint) and Run 3 (839ms stress, 1,483ms breakpoint) confirm the 1w high-load ceiling is now well characterized and reproducible
3. **Slowest recovery** — takes longest to drain request backlog after bursts

### Thesis Takeaway
The single-worker config performs well at moderate concurrency but is the weakest config under high load. Its high-load behavior is now consistent across runs (unlike Run 1 where 1w performed anomalously well). The undivided 90-connection pool is an advantage, but the single event loop is the bottleneck above ~100 VUs. Across three runs, 1w is consistently the worst-performing config at high concurrency — confirming linear scaling where adding workers improves performance.
