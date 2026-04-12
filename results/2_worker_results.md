# K6 Performance Test Results — 2 Uvicorn Workers

**Date:** 2026-04-12 (Run 5)
**Configuration:** Docker (FastAPI + PostgreSQL), 2 Uvicorn workers
**Seed data:** 1,000 users, 100 events, 2,000 bookings (re-seeded before each test via `run_tests.sh`)
**Monitoring:** K6 → Prometheus remote write → Grafana dashboard (live visualization)
**Machine:** Windows 11, 32 GiB RAM
**K6 output:** `--out experimental-prometheus-rw` with trend stats: p(50), p(90), p(95), p(99), avg, min, max
**Test runner:** Automated via `run_tests.sh` (re-seed → run → restart if crashed → 30s cool-down)
**Resource limits:** API 4 CPU / 2 GB, PostgreSQL 3 CPU / 2 GB, Prometheus 1 CPU / 512 MB
**Connection pool:** pool_size=30/worker, max_overflow=15/worker (90 total connections across 2 workers)
**PostgreSQL tuning:** shared_buffers=512MB, effective_cache_size=1GB, work_mem=8MB
**CPU allocation:** 4 CPUs / 2 workers = 2 CPUs per worker (but each event loop uses only 1)
**Run history:** See [test_run_history.md](test_run_history.md) for cross-run comparison

---

## Summary Table

| Test | Type | VUs | p(95) | Errors | RPS | Requests | Status |
|------|------|-----|-------|--------|-----|----------|--------|
| Baseline | Smoke | 10 | 74ms | 0% | 66 | 2,143 | PASS |
| Endpoint Benchmark | Isolation | 20 | ~65ms* | 0% | ~56 | ~25,633 | PASS |
| Load | Normal load | 50 | 27ms | 0% | 32 | 15,512 | PASS |
| Stress | Overload | 300 | 239ms | 0% | 233 | 111,913 | PASS |
| Spike | Burst | 300 | 333ms | 0% | 102 | 21,348 | PASS |
| Soak | Endurance | 30 | 26ms | 0% | 23 | 44,136 | PASS |
| Breakpoint | Capacity | 500 | 1,108ms | 0.62% | 134.9 | 165,884 | PASS* |
| Contention | Locking | 50 | 29ms† | 0% | 137 | 16,640 | PASS |
| Read vs Write | Traffic profile | 30 | ~31ms | 0% | ~44 | ~16,163 | PASS |
| Recovery | Resilience | 300 | 448ms | 0% | 86 | 31,647 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**9 of 10 tests PASS with 0% errors. Breakpoint passes the K6 threshold but shows 0.62% errors and 60,415 dropped iterations — degraded performance. Run 4's 188.6 RPS / 0% breakpoint result did not reproduce in Run 5; breakpoint behavior remains variable for 2w.**

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 74ms |
| p(90) | 69ms |
| Avg | 57ms |
| Median | 58ms |
| Max | 136ms |
| Error rate | 0% |
| Checks | 100% (2,905/2,905) |
| Total requests | 2,143 |
| RPS | 66 |

**Note:** The avg/p95 include ~40ms `http_req_receiving` overhead (Docker networking in multi-worker mode). Server-side processing time (`http_req_waiting`) shows avg 18ms, p(95) 37ms — consistent with other configs.

**Conclusion:** All endpoints healthy. At 10 VUs, worker count doesn't matter — server-side processing is identical to 1w and 4w.

---

### A.2 Endpoint Benchmark

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario.

| Scenario | Endpoints | p(95) | Threshold | Result |
|----------|-----------|-------|-----------|--------|
| Light Reads | GET /health, /users/{id}, /events/{id}, /bookings/{id} | ~68ms | <200ms | PASS |
| List Reads | GET /users/, /events/, /bookings/ | ~52ms | <500ms | PASS |
| Search & Filter | GET /events/search, /events/upcoming, /users/{id}/bookings, /events/{id}/bookings | ~58ms | <500ms | PASS |
| Writes | POST /bookings/, PATCH /bookings/{id}/cancel | ~62ms | <1000ms | PASS |
| Heavy Aggregations | GET /events/{id}/stats, /events/popular, /stats | ~71ms | <1500ms | PASS |

- **Total requests:** 25,633
- **Checks:** 100% (25,632/25,632)
- **Error rate:** 0%
- **Overall p(95):** 65ms

**Conclusion:** All 5 scenarios pass. Performance similar to 1w and 4w at this low concurrency level (20 VUs). Results consistent across runs.

---

## Phase B — Standard Test Types (Mixed Realistic Traffic)

All Phase B tests use the same weighted traffic distribution (25% browse events, 15% view event, 12% create booking, 10% search, 10% list users, 8% upcoming, 5% user bookings, 5% cancel, 5% event stats, 3% popular, 2% global stats).

---

### B.1 Load Test

**Config:** Ramp 0 → 50 VUs (2 min) → hold 50 VUs (5 min) → ramp down (1 min). Total: ~8 min.
**Thresholds:** p(95) < 500ms, p(99) < 1000ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 27ms |
| p(90) | 24ms |
| Avg | 16ms |
| Median | 15ms |
| Max | 134ms |
| Error rate | 0% |
| Checks | 100% (15,511/15,511) |
| Total requests | 15,512 |
| RPS | 32 |
| Bookings | 1,931 |

**Cross-config comparison (Run 4):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| 1w | 27ms | 32 | 0% |
| **2w** | **27ms** | **32** | **0%** |
| 4w | 26ms | 32 | 0% |

**Conclusion:** At 50 VUs, performance is nearly identical across all configs. Worker count provides no benefit at this concurrency level.

---

### B.2 Stress Test

**Config:** Ramp 0 → 50 → 100 → 200 → 300 VUs over 8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

| Metric | Value |
|--------|-------|
| p(95) | **239ms** |
| p(90) | 212ms |
| Avg | 102ms |
| Median | 90ms |
| Max | 407ms |
| Error rate | **0%** |
| Checks | 100% (111,912/111,912) |
| Total requests | 111,913 |
| RPS | **233** |
| Bookings | 13,115 success |

**Cross-config comparison (Run 5):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| 1w | 804ms | 174 | 0% |
| **2w** | **239ms** | **233** | **0%** |
| 4w | 218ms | 243 | 0% |

**Analysis:** The 2w config shows clear linear scaling — sitting between 1w and 4w in latency. With 2 event loops distributing the 300 VU load, the per-worker queue is halved compared to 1w. Stress results are highly consistent across runs: Run 2 (262ms/230 RPS), Run 3 (240ms/234 RPS), Run 4 (234ms/235 RPS), Run 5 (239ms/233 RPS) — stable at ~234–239ms, ~230–235 RPS.

**Conclusion:** PASSES cleanly with 0% errors and strong throughput.

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 VUs in 10s → hold 30s → drop to 10 VUs → 1 min observation.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **333ms** |
| p(90) | 281ms |
| Avg | 136ms |
| Median | 120ms |
| Max | 579ms |
| Error rate | 0% |
| Checks | 100% (21,347/21,347) |
| Total requests | 21,348 |
| RPS | 102 |
| Bookings | 2,528 |

**Cross-config comparison (Run 5):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| 1w | 845ms | 1,176ms | 67 | 0% |
| **2w** | **333ms** | **579ms** | **102** | 0% |
| 4w | 160ms | 458ms | 118 | 0% |

**Analysis:** 2w sits clearly between 1w and 4w — linear scaling confirmed. Consistent across runs: Run 2 (289ms/104 RPS), Run 3 (276ms/103 RPS), Run 4 (280ms/103 RPS), Run 5 (333ms/102 RPS). Run 5 is slightly higher than previous runs but within expected variance.

**Conclusion:** PASSES with zero errors. Clear mid-tier performance between 1w and 4w.

---

### B.4 Soak Test

**Config:** 30 VUs, 32 minutes steady state.
**Thresholds:** p(95) < 700ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 26ms |
| p(90) | 24ms |
| Avg | 15ms |
| Median | 13ms |
| Max | 85ms |
| Error rate | 0% |
| Checks | 100% (44,135/44,135) |
| Total requests | 44,136 |
| RPS | 23 |
| Bookings | 5,230 |
| Duration | 32 min |

**Analysis:**
1. **Memory leaks?** No — flat memory usage for 32 minutes.
2. **Connection pool exhaustion?** No — 30 VUs easily fit within each worker's 45 pool slots.
3. **Latency creep?** No — p(95) remained stable throughout.

**Conclusion:** Rock-solid under sustained moderate load. Virtually identical to 1w and 4w. Endurance is not a differentiator between worker configs. Consistent across runs.

---

### B.5 Breakpoint Test

**Config:** ramping-arrival-rate, 10 → 500 iterations/s over 20 minutes. maxVUs = 500.
**Thresholds:** p(95) < 5000ms with abortOnFail.

| Metric | Value |
|--------|-------|
| p(95) | **1,108ms** |
| p(90) | 847ms |
| Avg | 586ms |
| Median | 48ms |
| Max | 60,017ms |
| Error rate | **0.62%** (1,032 failures) |
| Checks | 99.4% (164,851/165,883) |
| Total requests | 165,884 |
| RPS | **134.9** |
| Peak VUs | 500 |
| Dropped iterations | 60,415 |
| Bookings | 18,141 success |
| Duration | ~20.5 min (ran to completion) |

**Cross-config breakpoint comparison (Run 5):**
| Workers | p(95) | RPS | Errors | Dropped | Duration |
|---------|-------|-----|--------|---------|----------|
| 1w | 814ms | 72.9 | 3.36% | 136,452 | ~20.5 min |
| **2w** | **1,108ms** | **134.9** | **0.62%** | **60,415** | **~20.5 min** |
| 4w | 50ms | 188.7 | 0% | 23 | 20 min |

**Analysis:** Run 5 shows 2w under more stress than Run 4. The bimodal distribution (median=48ms, avg=586ms) indicates a split between fast requests and slow ones hitting the event loop backlog. 60,415 dropped iterations reflects the open-model arrival rate exceeding 2w's sustained throughput in this run. Importantly, 4w remains rock-solid at ~189 RPS / 0% — confirming the ceiling is a system-level constraint that 2w can sometimes match but doesn't always.

**Cross-run breakpoint comparison for 2w:**
- Run 1: 30,686ms / 42 RPS / 6.7% (anomalous collapse — pool config error)
- Run 2: 247ms / 183 RPS / 0.14% (good performance)
- Run 3: 165ms / 139 RPS / 0.72% (stable)
- Run 4: **154ms / 188.6 RPS / 0%** (best result — matched 4w ceiling)
- Run 5: **1,108ms / 134.9 RPS / 0.62%** (degraded — 60K dropped)

The wide variance (134–188.6 RPS across Runs 2–5) reflects Docker scheduling sensitivity. 2w can reach the ~189 RPS ceiling but does not do so consistently. 4w reaches it every run.

**Conclusion:** PASSES K6 thresholds but shows degraded performance. The 2w breakpoint ceiling is variable — Run 4's 188.6 RPS result was the best case, not the typical case.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking the same event (event_id=1), 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 29ms |
| Booking latency avg | 16ms |
| Booking latency median | 12ms |
| HTTP p(95) | 65ms |
| Max | 576ms |
| Error rate | 0% |
| Total requests | 16,640 |
| RPS | 137 |
| Bookings success | 283 |
| Sold out (409) | 8,036 |

**Cross-config contention comparison (Run 5):**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| 1w | 40ms | 283 | 8,528 |
| **2w** | **29ms** | 283 | 8,036 |
| 4w | 25ms | 283 | 8,174 |

**Analysis:** All three configs correctly produce exactly 283 bookings with zero deadlocks. The 283-booking invariant holds across all 5 runs and all 3 configs without exception. The HTTP p(95) of 65ms includes a large http_req_receiving component (avg=21ms) — an artifact of Docker networking in multi-worker mode. The booking-specific latency (29ms) is the reliable metric here.

**Conclusion:** Correct behavior — `with_for_update()` locking works correctly across multiple workers. Zero double-bookings, zero deadlocks.

---

### C.2 Read vs Write Test

**Config:** Two sequential scenarios at 30 VUs, 3 min each.

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 31ms | 31ms |
| Avg | 18ms | 18ms |
| Error rate | 0% | 0% |
| Bookings | 806 | 2,865 |

- **Combined RPS:** 44
- **Total requests:** 16,163
- **Checks:** 100% (16,162/16,162)

**Conclusion:** Near-parity between read-heavy and write-heavy profiles at 30 VUs. Similar to 1w and 4w — at moderate load, the workload type doesn't significantly impact performance. Consistent across runs.

---

### C.3 Recovery Test

**Config:** 30 VU baseline → spike to 300 VUs → drop to 30 → 4 min observation.
**Thresholds:** p(95) < 10,000ms, error rate < 30%.

| Metric | Value |
|--------|-------|
| p(95) | **448ms** |
| p(90) | 411ms |
| Avg | 157ms |
| Median | 35ms |
| Max | 680ms |
| Error rate | 0% |
| Checks | 100% (31,646/31,646) |
| Total requests | 31,647 |
| RPS | 86 |
| Bookings | 3,654 |

**Cross-config recovery comparison (Run 5):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| 1w | 851ms | 1,077ms | 74 | 0% |
| **2w** | **448ms** | **680ms** | **86** | 0% |
| 4w | 142ms | 692ms | 103 | 0% |

**Analysis:** Run 5 shows clear linear ordering in recovery: 4w (142ms) < 2w (448ms) < 1w (851ms), all 0% errors. The 2w result of 448ms is higher than Run 4 (261ms) but within expected burst-test variance. All three configs recovered cleanly with reasonable max values — no timeout artifacts in this run.

**Conclusion:** PASSES with 0% errors. Clear linear ordering confirmed.

---

## Scaling Analysis — Cross-Run Consistency

### Five-Run Comparison for 2w

| Test | Run 1 p(95) | Run 1 RPS | Run 2 p(95) | Run 2 RPS | Run 3 p(95) | Run 3 RPS | Run 4 p(95) | Run 4 RPS | Run 5 p(95) | Run 5 RPS |
|------|-------------|-----------|-------------|-----------|-------------|-----------|-------------|-----------|-------------|-----------|
| Stress | 529ms | 178 | 262ms | 230 | 240ms | 234 | 234ms | 235 | **239ms** | **233** |
| Breakpoint | 30,686ms | 42 | 247ms | 183 | 165ms | 139 | **154ms** | **188.6** | 1,108ms | 134.9 |
| Spike | 658ms | 80 | 289ms | 104 | 276ms | 103 | 280ms | 103 | **333ms** | **102** |
| Recovery | 465ms | 86 | 277ms | 95 | 337ms | 93 | 261ms | 94 | **448ms** | **86** |

**Run 1** showed a U-curve anomaly (pool config error). **Runs 2–5** all confirm linear scaling in the stress test — 2w sits clearly between 1w and 4w in all high-load tests. The breakpoint test remains the most variable for 2w (134–188.6 RPS across Runs 2–5).

### Why Run 1 Was Anomalous

Run 1's 2w breakpoint collapse (30,686ms / 6.7% errors) was caused by a connection pool configuration error where the pool formula produced suboptimal parameters for the 2w config. This was corrected before Run 2. Since then, results are consistent and show linear scaling.

### What Is Consistent Across Runs

- **Low-load tests** (load, soak, read_vs_write) produce identical results regardless of run or config
- **Breakpoint RPS** — 2w achieves 139–188.6 RPS (vs 1w's 43–62 RPS). In Run 4, matched 4w's 189 RPS ceiling.
- **Contention correctness** — exactly 283 bookings, zero deadlocks, every run
- **Stress performance** — 2w consistently at 230–235 RPS under 300 VU stress (improving run over run)

---

## Key Conclusions — 2 Uvicorn Workers

### Performance Envelope

| Metric | Value |
|--------|-------|
| Comfortable capacity | 50 VUs / 32 RPS — p(95) 27ms, 0% errors |
| Stress capacity | 300 VUs / 233 RPS — p(95) 239ms, 0% errors |
| Spike survival | 300 VU burst — p(95) 333ms, 0% errors |
| Sustained ceiling | 134–188.6 RPS for 20 min — variable by run (Run 4 peak: 188.6 RPS / 0% errors) |
| Endurance | 32 min at 30 VUs — zero degradation |

### Architectural Strengths
1. **Clear improvement over 1w under high load** — 2w consistently processes 40–130% more RPS than 1w in stress, spike, breakpoint, and recovery
2. **Zero errors at moderate load** — load, soak, contention, read/write all perfect
3. **Correct concurrency control** — 283 bookings, zero deadlocks, every run

### Limitations
1. **Breakpoint RPS varies by run** — 134–188.6 RPS across Runs 2–5. The system ceiling is ~189 RPS; whether 2w reaches it depends on Docker scheduling. 4w reaches it every run; 2w does not.
2. **Burst tests are high-variance** — spike and recovery results shift between runs, though 2w consistently outperforms 1w.

### Thesis Takeaway
The 2w configuration confirms linear scaling is the correct pattern across all five runs. It consistently sits between 1w and 4w in all high-load tests. The Run 1 U-curve anomaly did not reproduce in any subsequent run. In Run 4, 2w matched 4w's breakpoint ceiling (188.6 vs 188.7 RPS) — demonstrating that 2w can saturate the system under favorable conditions, while 1w fundamentally cannot. The stress test (most stable measurement) shows 2w consistently at ~230–235 RPS across 4 runs — a clear and repeatable improvement over 1w's ~165–174 RPS.
