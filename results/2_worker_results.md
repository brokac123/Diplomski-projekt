# K6 Performance Test Results — 2 Uvicorn Workers

**Date:** 2026-04-09 (Run 2)
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
| Baseline | Smoke | 10 | 72ms | 0% | 68 | 2,171 | PASS |
| Endpoint Benchmark | Isolation | 20 | ~74ms* | 0% | ~54 | ~25,000 | PASS |
| Load | Normal load | 50 | 28ms | 0% | 32 | 15,431 | PASS |
| Stress | Overload | 300 | 262ms | 0% | 230 | 110,369 | PASS |
| Spike | Burst | 300 | 289ms | 0% | 104 | 21,804 | PASS |
| Soak | Endurance | 30 | 25ms | 0% | 23 | 44,179 | PASS |
| Breakpoint | Capacity | 500 | 247ms | 0.14% | 183 | 224,694 | PASS |
| Contention | Locking | 50 | 33ms† | 0% | 138 | 16,678 | PASS |
| Read vs Write (read) | Traffic profile | 30 | ~30ms | 0% | ~43 | ~8,100 | PASS |
| Read vs Write (write) | Traffic profile | 30 | ~32ms | 0% | ~43 | ~8,100 | PASS |
| Recovery | Resilience | 300 | 277ms | 0% | 95 | 35,251 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**All 10 tests PASS. Breakpoint has 0.14% errors (307 failures out of 224K requests) but passes all K6 thresholds.**

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 72ms |
| p(90) | 68ms |
| Avg | 56ms |
| Median | 58ms |
| Max | 130ms |
| Error rate | 0% |
| Checks | 100% (2,945/2,945) |
| Total requests | 2,171 |
| RPS | 68 |
| Iterations | 155 |

**Note:** The avg/p95 include ~40ms `http_req_receiving` overhead (likely Docker networking in multi-worker mode). Server-side processing time (`http_req_waiting`) shows avg 17ms, p(95) 30ms — consistent with other configs.

**Conclusion:** All endpoints healthy. At 10 VUs, worker count doesn't matter — performance is identical to 1w and 4w.

---

### A.2 Endpoint Benchmark

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario.

| Scenario | Endpoints | p(95) | Threshold | Result |
|----------|-----------|-------|-----------|--------|
| Light Reads | GET /health, /users/{id}, /events/{id}, /bookings/{id} | ~78ms | <200ms | PASS |
| List Reads | GET /users/, /events/, /bookings/ | ~62ms | <500ms | PASS |
| Search & Filter | GET /events/search, /events/upcoming, /users/{id}/bookings, /events/{id}/bookings | ~59ms | <500ms | PASS |
| Writes | POST /bookings/, PATCH /bookings/{id}/cancel | ~71ms | <1000ms | PASS |
| Heavy Aggregations | GET /events/{id}/stats, /events/popular, /stats | ~82ms | <1500ms | PASS |

- **Total requests:** ~25,000
- **Checks:** 100%
- **Error rate:** 0%

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
| p(95) | 28ms |
| p(90) | 25ms |
| Avg | 16ms |
| Median | 15ms |
| Max | 84ms |
| Error rate | 0% |
| Checks | 100% (15,430/15,430) |
| Total requests | 15,431 |
| RPS | 32 |
| Bookings | 1,933 |

**Conclusion:** At 50 VUs, performance is nearly identical to 1w (28ms) and 4w (27ms). Worker count provides no benefit at this concurrency level.

---

### B.2 Stress Test

**Config:** Ramp 0 → 50 → 100 → 200 → 300 VUs over 8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

| Metric | Value |
|--------|-------|
| p(95) | **262ms** |
| p(90) | 228ms |
| Avg | 110ms |
| Median | 94ms |
| Max | 647ms |
| Error rate | **0%** |
| Checks | 100% (110,368/110,368) |
| Total requests | 110,369 |
| RPS | **230** |
| Bookings | 12,679 success / 612 sold out |

**Cross-config comparison (Run 2):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| 1w | 886ms | 164 | 0% |
| **2w** | **262ms** | **230** | **0%** |
| 4w | 177ms | 248 | 0% |

**Analysis:** The 2w config shows clear linear scaling — sitting between 1w and 4w in both latency and throughput. With 262ms p(95) and 230 RPS, it handles 300 VUs comfortably. This is a significant improvement over Run 1 (529ms / 178 RPS), demonstrating run-to-run variance in high-load tests.

**Conclusion:** PASSES cleanly with 0% errors and strong throughput.

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 VUs in 10s → hold 30s → drop to 10 VUs → 1 min observation.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **289ms** |
| p(90) | 257ms |
| Avg | 123ms |
| Median | 109ms |
| Max | 411ms |
| Error rate | 0% |
| Checks | 100% (21,803/21,803) |
| Total requests | 21,804 |
| RPS | 104 |
| Bookings | 2,591 |

**Cross-config comparison (Run 2):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| 1w | 1,225ms | 1,412ms | 62 | 0% |
| **2w** | **289ms** | **411ms** | **104** | 0% |
| 4w | 609ms | 1,378ms | 98 | 0% |

**Analysis:** In this run, 2w actually outperformed 4w on the spike test — lower p(95) (289ms vs 609ms) and higher RPS (104 vs 98). This suggests that the 2-worker config can handle sudden bursts effectively when Docker CPU scheduling favors it. The result is not consistent across runs (Run 1 showed the opposite), highlighting the variance in burst-handling tests.

**Conclusion:** PASSES with zero errors and the best spike performance of all configs in this run.

---

### B.4 Soak Test

**Config:** 30 VUs, 32 minutes steady state.
**Thresholds:** p(95) < 700ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 25ms |
| p(90) | 22ms |
| Avg | 14ms |
| Median | 13ms |
| Max | 96ms |
| Error rate | 0% |
| Checks | 100% (44,178/44,178) |
| Total requests | 44,179 |
| RPS | 23 |
| Bookings | 5,299 |
| Duration | 32 min |

**Analysis:**
1. **Memory leaks?** No — flat memory usage for 32 minutes.
2. **Connection pool exhaustion?** No — 30 VUs easily fit within each worker's 45 pool slots.
3. **Latency creep?** No — p(95) remained stable throughout.

**Conclusion:** Rock-solid under sustained moderate load. Virtually identical to 1w (27ms) and 4w (27ms). Endurance is not a differentiator between worker configs. Consistent across runs.

---

### B.5 Breakpoint Test

**Config:** ramping-arrival-rate, 10 → 500 iterations/s over 20 minutes. maxVUs = 500.
**Thresholds:** p(95) < 5000ms with abortOnFail.

| Metric | Value |
|--------|-------|
| p(95) | **247ms** |
| p(90) | 156ms |
| Avg | 136ms |
| Median | 18ms |
| Max | 60,004ms |
| Error rate | **0.14%** (307 failures) |
| Total requests | 224,694 |
| RPS | **183** |
| Peak VUs | 500 |
| Dropped iterations | **1,599** |
| Bookings | 22,803 success / 4,277 sold out / 38 failed |
| Duration | ~20.5 min (full run) |

**Cross-config breakpoint comparison (Run 2):**
| Workers | p(95) | RPS | Errors | Peak VUs | Dropped | Duration |
|---------|-------|-----|--------|----------|---------|----------|
| 1w | 1,464ms | 62 | 4.6% | 500 | 149,646 | ~20.5 min |
| **2w** | **247ms** | **183** | **0.14%** | 500 | **1,599** | ~20.5 min |
| 4w | 112ms | 189 | 0% | 164 | 118 | 20 min |

**Analysis:** A dramatic improvement over Run 1 (30,686ms / 42 RPS / 6.7% errors). In Run 2, the 2w config handled the breakpoint test nearly as well as 4w — 183 RPS vs 189 RPS with only 0.14% errors. The 1,599 dropped iterations (vs 149K for 1w) show the system mostly kept up with the arrival rate.

The max of 60,004ms and 307 failures suggest a few requests hit timeout under peak load, but the vast majority completed quickly (median 18ms). The bimodal distribution (median 18ms vs p95 247ms) indicates that most requests were fast, with a tail of slower requests during peak ramp.

**Conclusion:** PASSES all thresholds. Near-production quality result with 183 RPS sustained for 20 minutes.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking the same event (event_id=1), 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 33ms |
| Booking latency avg | 16ms |
| Booking latency median | 12ms |
| HTTP p(95) | 66ms |
| Max | 500ms |
| Error rate | 0% |
| Total requests | 16,678 |
| RPS | 138 |
| Bookings success | 283 |
| Sold out (409) | 8,055 |

**Cross-config contention comparison (Run 2):**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| 1w | 43ms | 283 | 8,460 |
| 2w | 33ms | 283 | 8,055 |
| 4w | 35ms | 283 | 8,018 |

**Analysis:** All three configs correctly produce exactly 283 bookings with zero deadlocks. Booking latency is similar across configs — the row lock serialization means only one transaction succeeds at a time regardless of worker count. Results are consistent across runs.

**Conclusion:** Correct behavior — `with_for_update()` locking works correctly across multiple workers. Zero double-bookings, zero deadlocks.

---

### C.2 Read vs Write Test

**Config:** Two sequential scenarios at 30 VUs, 3 min each.

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | ~30ms | ~32ms |
| Avg | ~18ms | ~19ms |
| Error rate | 0% | 0% |
| Bookings | ~804 | ~2,799 |

- **Combined RPS:** ~43
- **Checks:** 100%

**Conclusion:** Near-parity between read-heavy and write-heavy profiles at 30 VUs. Similar to 1w and 4w — at moderate load, the workload type doesn't significantly impact performance. Consistent across runs.

---

### C.3 Recovery Test

**Config:** 30 VU baseline → spike to 300 VUs → drop to 30 → 4 min observation.
**Thresholds:** p(95) < 10,000ms, error rate < 30%.

| Metric | Value |
|--------|-------|
| p(95) | **277ms** |
| p(90) | 238ms |
| Avg | 89ms |
| Median | 35ms |
| Max | 450ms |
| Error rate | 0% |
| Checks | 100% (35,250/35,250) |
| Total requests | 35,251 |
| RPS | 95 |
| Bookings | 4,316 |

**Cross-config recovery comparison (Run 2):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| 1w | 938ms | 1,521ms | 72 | 0% |
| **2w** | **277ms** | **450ms** | **95** | 0% |
| 4w | 539ms | 1,361ms | 92 | 0% |

**Analysis:** In this run, 2w outperformed 4w on recovery — lower p(95) (277ms vs 539ms) and slightly higher RPS (95 vs 92). Similar to the spike test, the 2w config handled the burst-then-recover pattern well. The median of 35ms indicates the system returns to baseline quickly after the spike.

**Conclusion:** PASSES with 0% errors and the best recovery performance in this run.

---

## Scaling Analysis — Run Variance

### Run 1 vs Run 2: Different Patterns

The 2w configuration showed drastically different behavior between the two runs:

| Test | Run 1 p(95) | Run 1 RPS | Run 2 p(95) | Run 2 RPS |
|------|-------------|-----------|-------------|-----------|
| Stress | 529ms | 178 | **262ms** | **230** |
| Breakpoint | **30,686ms** | 42 | 247ms | 183 |
| Spike | 658ms | 80 | **289ms** | **104** |
| Recovery | 465ms | 86 | **277ms** | **95** |

**Run 1** showed a U-curve pattern where 2w was the worst config. **Run 2** shows roughly linear scaling where 2w sits between 1w and 4w (and even outperforms 4w on spike/recovery).

### Why Results Vary Between Runs

The high-load tests are sensitive to:
1. **Docker CPU scheduling** — how the OS allocates CPU time slices to containers varies between runs
2. **Background OS load** — Windows services, antivirus, and other processes compete for CPU time
3. **Connection pool timing** — the exact order in which connections are allocated and returned affects queueing behavior under load
4. **Database cache state** — PostgreSQL's buffer pool warmth at the start of each test depends on the previous test's workload

### What Is Consistent Across Runs

- **Low-load tests** (load, soak, read_vs_write, contention) produce identical results regardless of run or config
- **4w is consistently the best** under sustained high throughput (breakpoint)
- **All configs handle 50 VUs** with identical sub-30ms p95 latency
- **Contention correctness** — exactly 283 bookings, zero deadlocks, every run

### Thesis Implication

Single-run test results are insufficient for drawing conclusions about scaling patterns. The dramatic difference between Run 1 and Run 2 (2w breakpoint: 30,686ms → 247ms) demonstrates that performance testing must include multiple iterations. The test_run_history.md tracks each run to build a more accurate picture over time.

---

## Key Conclusions — 2 Uvicorn Workers (Run 2)

### Performance Envelope

| Metric | Value |
|--------|-------|
| Comfortable capacity | 50 VUs / 32 RPS — p(95) 28ms, 0% errors |
| Stress capacity | 300 VUs / 230 RPS — p(95) 262ms, 0% errors |
| Spike survival | 300 VU burst — p(95) 289ms, 0% errors |
| Sustained ceiling | 183 RPS for 20 min — p(95) 247ms, 0.14% errors |
| Endurance | 32 min at 30 VUs — zero degradation |

### Thesis Takeaway

The 2w configuration's performance varies significantly between runs. In Run 1, it exhibited a U-curve pattern (worst under high load). In Run 2, it showed expected linear scaling (between 1w and 4w). This variance highlights that **performance testing conclusions require multiple iterations**, not single runs. The consistent finding across both runs is that 4w provides the most reliable high-load performance, while worker count is irrelevant at moderate concurrency (≤50 VUs).
