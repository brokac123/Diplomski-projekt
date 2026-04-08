# K6 Performance Test Results — 2 Uvicorn Workers

**Date:** 2026-04-08
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

---

## Summary Table

| Test | Type | VUs | p(95) | Errors | RPS | Requests | Status |
|------|------|-----|-------|--------|-----|----------|--------|
| Baseline | Smoke | 10 | 80ms | 0% | 16 | 659 | PASS |
| Endpoint Benchmark | Isolation | 20 | 74ms* | 0% | 54 | 25,040 | PASS |
| Load | Normal load | 50 | 34ms | 0% | 32 | 15,306 | PASS |
| Stress | Overload | 300 | 529ms | 0.14% | 178 | 85,395 | PASS |
| Spike | Burst | 300 | 658ms | 0% | 80 | 16,895 | PASS |
| Soak | Endurance | 30 | 29ms | 0% | 23 | 43,902 | PASS |
| Breakpoint | Capacity | 500 | 30,686ms | 6.7% | 42 | 38,277 | **FAIL** |
| Contention | Locking | 50 | 33ms† | 0% | 137 | 16,574 | PASS |
| Read vs Write (read) | Traffic profile | 30 | 34ms | 0% | 43 | ~8,100 | PASS |
| Read vs Write (write) | Traffic profile | 30 | 36ms | 0% | 43 | ~8,100 | PASS |
| Recovery | Resilience | 300 | 465ms | 0% | 86 | 31,884 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**9 of 10 tests PASS. Breakpoint FAILS (p(95) 30,686ms, 6.7% errors, 69K dropped iterations).**

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 80ms |
| p(90) | 72ms |
| Avg | 507ms (skewed by one slow send) |
| Median | 56ms |
| Max | 30,187ms |
| Error rate | 0% |
| Checks | 100% (893/893) |
| Total requests | 659 |
| RPS | 16 |
| Iterations | 47 |

**Note:** The avg/max are skewed by a single slow `http_req_sending` outlier (30s). The server-side processing time (`http_req_waiting`) shows avg 18ms, p(95) 43ms — consistent with other configs.

**Conclusion:** All endpoints healthy. At 10 VUs, worker count doesn't matter — performance is identical to 1w and 4w.

---

### A.2 Endpoint Benchmark

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario.

| Scenario | Endpoints | p(95) | Threshold | Result |
|----------|-----------|-------|-----------|--------|
| Light Reads | GET /health, /users/{id}, /events/{id}, /bookings/{id} | 78ms | <200ms | PASS |
| List Reads | GET /users/, /events/, /bookings/ | 62ms | <500ms | PASS |
| Search & Filter | GET /events/search, /events/upcoming, /users/{id}/bookings, /events/{id}/bookings | 59ms | <500ms | PASS |
| Writes | POST /bookings/, PATCH /bookings/{id}/cancel | 71ms | <1000ms | PASS |
| Heavy Aggregations | GET /events/{id}/stats, /events/popular, /stats | 82ms | <1500ms | PASS |

- **Total requests:** 25,040
- **Checks:** 100% (25,039/25,039)
- **Error rate:** 0%

**Conclusion:** All 5 scenarios pass. Performance similar to 1w and 4w at this low concurrency level (20 VUs).

---

## Phase B — Standard Test Types (Mixed Realistic Traffic)

All Phase B tests use the same weighted traffic distribution (25% browse events, 15% view event, 12% create booking, 10% search, 10% list users, 8% upcoming, 5% user bookings, 5% cancel, 5% event stats, 3% popular, 2% global stats).

---

### B.1 Load Test

**Config:** Ramp 0 → 50 VUs (2 min) → hold 50 VUs (5 min) → ramp down (1 min). Total: ~8 min.
**Thresholds:** p(95) < 500ms, p(99) < 1000ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 34ms |
| p(90) | 29ms |
| Avg | 19ms |
| Median | 17ms |
| Max | 175ms |
| Error rate | 0% |
| Checks | 100% (15,305/15,305) |
| Total requests | 15,306 |
| RPS | 32 |
| Bookings | 1,793 |

**Conclusion:** At 50 VUs, the system operates comfortably. Performance is nearly identical to 1w (28ms) and 4w (27ms). Worker count provides no benefit at this concurrency level.

---

### B.2 Stress Test

**Config:** Ramp 0 → 50 → 100 → 200 → 300 VUs over 8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

| Metric | Value |
|--------|-------|
| p(95) | **529ms** |
| p(90) | 432ms |
| Avg | 287ms |
| Median | 133ms |
| Max | 41,630ms |
| Error rate | **0.14%** (122 failures) |
| Checks | 99.86% (85,272/85,394) |
| Total requests | 85,395 |
| RPS | **178** |
| Bookings | 9,880 success / 155 sold out |

**Cross-config comparison:**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| 1w | 151ms | 251 | 0% |
| **2w** | **529ms** | **178** | **0.14%** |
| 4w | 129ms | 255 | 0% |

**Analysis:** The 2w config is **3.5x slower** than 1w and the only config with errors under stress. This is the first clear evidence of the U-curve pattern. With 300 VUs, one worker can become overloaded while the other has spare capacity — but they can't share connections across their separate pools (45 each). Meanwhile, 1w has all 90 connections in one pool, and 4w processes requests fast enough (4 event loops on 4 CPUs) that smaller pools don't matter.

**Conclusion:** PASSES but significantly underperforms both 1w and 4w.

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 VUs in 10s → hold 30s → drop to 10 VUs → 1 min observation.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **658ms** |
| p(90) | 586ms |
| Avg | 304ms |
| Median | 312ms |
| Max | 962ms |
| Error rate | 0% |
| Checks | 100% (16,894/16,894) |
| Total requests | 16,895 |
| RPS | 80 |
| Bookings | 2,033 |

**Cross-config comparison:**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| 1w | 525ms | 1,441ms | 102 | 0% |
| **2w** | **658ms** | 962ms | **80** | 0% |
| 4w | 155ms | 310ms | 117 | 0% |

**Analysis:** 2w has the highest p(95) during the spike (658ms vs 525ms 1w, 155ms 4w) and the lowest RPS (80). The lower max vs 1w (962ms vs 1,441ms) suggests the 2 workers do absorb peak bursts slightly better than 1, but overall throughput suffers due to per-worker pool limits.

**Conclusion:** PASSES with zero errors but recovers more slowly than both 1w and 4w.

---

### B.4 Soak Test

**Config:** 30 VUs, 32 minutes steady state.
**Thresholds:** p(95) < 700ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 29ms |
| p(90) | 27ms |
| Avg | 17ms |
| Median | 15ms |
| Max | 283ms |
| Error rate | 0% |
| Checks | 100% (43,901/43,901) |
| Total requests | 43,902 |
| RPS | 23 |
| Bookings | 5,225 |
| Duration | 32 min |

**Analysis:**
1. **Memory leaks?** No — flat memory usage for 32 minutes.
2. **Connection pool exhaustion?** No — 30 VUs easily fit within each worker's 45 pool slots.
3. **Latency creep?** No — p(95) remained stable throughout.

**Conclusion:** Rock-solid under sustained moderate load. Virtually identical to 1w (28ms) and 4w (27ms). Endurance is not a differentiator between worker configs.

---

### B.5 Breakpoint Test

**Config:** ramping-arrival-rate, 10 → 500 iterations/s over 20 minutes. maxVUs = 500.
**Thresholds:** p(95) < 5000ms with abortOnFail.

| Metric | Value |
|--------|-------|
| p(95) | **30,686ms** |
| p(90) | 67ms |
| Avg | 2,945ms |
| Median | 21ms |
| Max | 90,425ms |
| Error rate | **6.7%** (2,565 failures) |
| Total requests | 38,277 |
| RPS | **42** |
| Peak VUs | **500 (maxed out)** |
| Dropped iterations | **69,521** |
| Bookings | 4,294 success / 322 fail |
| Duration | ~15 min |

**Threshold result:** **FAIL** — p(95) of 30,686ms exceeds the 5,000ms threshold.

**Cross-config breakpoint comparison:**
| Workers | p(95) | RPS | Errors | Peak VUs | Dropped | Duration |
|---------|-------|-----|--------|----------|---------|----------|
| 1w | 192ms | 189 | 0% | 154 | 134 | 20 min (full) |
| **2w** | **30,686ms** | **42** | **6.7%** | **500** | **69,521** | **~15 min** |
| 4w | 106ms | 189 | 0% | 58 | 8 | 20 min (full) |

**Analysis:** This is the strongest evidence of the U-curve. The 2w config collapses under sustained high throughput:
- **RPS of 42** vs 189 for both 1w and 4w — 4.5x lower throughput
- **69,521 dropped iterations** — K6 couldn't send requests fast enough because VUs were stuck waiting
- **Bimodal latency:** median 21ms (successful requests) but p(95) 30,686ms (requests stuck in queue)
- **500 VUs maxed out** — all VUs were occupied waiting for responses, while 1w needed only 154 and 4w only 58

**Why 2w fails here:** Under open-model load (ramping-arrival-rate), the system must process requests at the arrival rate or fall behind. With 2 workers:
1. Each worker's pool (45 connections) saturates under high arrival rates
2. Once a pool is full, incoming requests queue inside the worker
3. Unlike 1w (which has 90 connections all available) or 4w (which processes so fast connections free up quickly), 2w hits a middle ground where pools are too small and CPU utilization too low
4. The queue grows, latency spikes, timeouts cascade

**Conclusion:** **FAIL.** The 2w config cannot sustain high throughput. This is the defining result of the U-curve scaling pattern.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking the same event (event_id=1), 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 33ms |
| Booking latency avg | 17ms |
| Booking latency median | 12ms |
| HTTP p(95) | 67ms |
| Max | 563ms |
| Error rate | 0% |
| Total requests | 16,574 |
| RPS | 137 |
| Bookings success | 283 |
| Sold out (409) | 8,003 |

**Cross-config contention comparison:**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| 1w | 29ms | 283 | 8,050 |
| 2w | 33ms | 283 | 8,003 |
| 4w | 25ms | 283 | 8,062 |

**Analysis:** All three configs correctly produce exactly 283 bookings with zero deadlocks. The 2w booking latency (33ms) sits between 1w (29ms) and 4w (25ms) — close to expected ordering. Under contention, the row lock serialization means only one transaction succeeds at a time regardless of worker count, so the differences are small.

**Conclusion:** Correct behavior — `with_for_update()` locking works correctly across multiple workers. Zero double-bookings, zero deadlocks.

---

### C.2 Read vs Write Test

**Config:** Two sequential scenarios at 30 VUs, 3 min each.

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 34ms | 36ms |
| Avg | 20ms | 21ms |
| Error rate | 0% | 0% |
| Bookings | 823 | 2,799 |

- **Combined RPS:** 43
- **Checks:** 100% (16,106/16,106)

**Conclusion:** Near-parity between read-heavy and write-heavy profiles at 30 VUs. Similar to 1w and 4w — at moderate load, the workload type doesn't significantly impact performance.

---

### C.3 Recovery Test

**Config:** 30 VU baseline → spike to 300 VUs → drop to 30 → 4 min observation.
**Thresholds:** p(95) < 10,000ms, error rate < 30%.

| Metric | Value |
|--------|-------|
| p(95) | 465ms |
| p(90) | 415ms |
| Avg | 152ms |
| Median | 37ms |
| Max | 712ms |
| Error rate | 0% |
| Checks | 100% (31,883/31,883) |
| Total requests | 31,884 |
| RPS | 86 |
| Bookings | 3,906 |

**Cross-config recovery comparison:**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| 1w | 521ms | 1,459ms | 93 | 0% |
| 2w | 465ms | 712ms | 86 | 0% |
| 4w | **137ms** | **329ms** | **103** | 0% |

**Analysis:** 2w recovery (465ms) is similar to 1w (521ms) — both handle the spike-then-recover pattern. The lower max (712ms vs 1,459ms) suggests 2 workers absorb the spike peak slightly better than 1, but overall throughput (86 RPS) is the lowest. 4w clearly outperforms both with 137ms p(95).

**Conclusion:** PASSES with 0% errors and full recovery. The median of 37ms indicates the system returns to baseline quickly after the spike ends.

---

## The U-Curve: Why 2 Workers Performs Worst

The 2w results reveal a **non-linear scaling pattern**. Instead of 2w performing between 1w and 4w, it performs worst under high concurrency:

```
Performance under high load (300+ VUs):

  Best ←————————————→ Worst
  4w       1w       2w
```

### Root Cause: Neither Advantage

The 2w config sits in a "worst of both worlds" position:

**1w has the undivided connection pool.**
Each Uvicorn worker is a single-threaded event loop that can only use 1 CPU core. With 1 worker on 4 CPUs, 3 CPUs are wasted — but the single event loop has all 90 database connections (pool_size=60 + overflow=30) available. Under 300 VU load, it can use any of those 90 connections freely, with no fragmentation.

**4w has full CPU utilization.**
With 4 workers on 4 CPUs, each worker gets 1:1 CPU mapping. Even though each worker only has 22 connections (pool_size=15 + overflow=7), the 4 event loops process requests so fast that connections are returned to the pool quickly. The CPU advantage overcomes the smaller per-worker pool.

**2w gets neither benefit.**
- Only 2 of 4 CPUs are utilized (50% waste) — not enough parallelism to compensate for pool splitting
- Each worker has 45 connections (pool_size=30 + overflow=15) — not as large as 1w's 90
- Under burst load, the OS load balancer distributes connections across workers, but this distribution can be uneven. One worker may exhaust its pool while the other has spare capacity — and they can't share.

### Evidence Summary

| Test | 1w | 2w | 4w | 2w vs best |
|------|-----|-----|-----|-----------|
| Stress p(95) | 151ms | 529ms | 129ms | 4.1x worse |
| Stress RPS | 251 | 178 | 255 | 1.4x lower |
| Spike p(95) | 525ms | 658ms | 155ms | 4.2x worse |
| Breakpoint p(95) | 192ms | 30,686ms | 106ms | **160x worse** |
| Breakpoint RPS | 189 | 42 | 189 | **4.5x lower** |
| Recovery p(95) | 521ms | 465ms | 137ms | 3.4x worse |

### Where Workers Don't Matter

At low concurrency (50 VUs or fewer), all three configs perform identically:
- Load test: 34ms vs 28ms vs 27ms (all within noise)
- Soak test: 29ms vs 28ms vs 27ms
- Read vs Write: 34/36ms vs 30/30ms vs 29/28ms

The multi-worker advantage only appears above ~100 VUs, and only when the worker count matches the available CPU cores (1:1 ratio).

---

## Key Conclusions — 2 Uvicorn Workers (New Infrastructure)

### Performance Envelope

| Metric | Value |
|--------|-------|
| Comfortable capacity | 50 VUs / 32 RPS — p(95) 34ms, 0% errors |
| Stress capacity | 300 VUs / 178 RPS — p(95) 529ms, 0.14% errors |
| Spike survival | 300 VU burst — p(95) 658ms, 0% errors, full recovery |
| Sustained ceiling | **42 RPS** (breakpoint FAIL — 6.7% errors, 69K dropped) |
| Endurance | 32 min at 30 VUs — zero degradation |

### Thesis Takeaway

**Worker count must match CPU cores for optimal performance.** Adding workers without a 1:1 CPU-to-worker ratio can degrade performance compared to a single worker. The optimal configuration for this 4-CPU setup is 4 workers, not 2. A single worker with access to the full connection pool outperforms 2 workers that split the pool without gaining sufficient CPU parallelism.
