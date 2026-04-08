# K6 Performance Test Results — 4 Uvicorn Workers

**Date:** 2026-04-08
**Configuration:** Docker (FastAPI + PostgreSQL), 4 Uvicorn workers
**Seed data:** 1,000 users, 100 events, 2,000 bookings (re-seeded before each test via `run_tests.sh`)
**Monitoring:** K6 → Prometheus remote write → Grafana dashboard (live visualization)
**Machine:** Windows 11, 32 GiB RAM
**K6 output:** `--out experimental-prometheus-rw` with trend stats: p(50), p(90), p(95), p(99), avg, min, max
**Test runner:** Automated via `run_tests.sh` (re-seed → run → restart if crashed → 30s cool-down)
**Resource limits:** API 4 CPU / 2 GB, PostgreSQL 3 CPU / 2 GB, Prometheus 1 CPU / 512 MB
**Connection pool:** pool_size=15/worker, max_overflow=7/worker (88 total connections across 4 workers)
**PostgreSQL tuning:** shared_buffers=512MB, effective_cache_size=1GB, work_mem=8MB
**CPU allocation:** 4 CPUs / 4 workers = 1 CPU per worker (1:1 ratio)

---

## Summary Table

| Test | Type | VUs | p(95) | Errors | RPS | Requests | Status |
|------|------|-----|-------|--------|-----|----------|--------|
| Baseline | Smoke | 10 | 75ms | 0% | 64 | 2,087 | PASS |
| Endpoint Benchmark | Isolation | 20 | 64ms* | 0% | 53 | 24,475 | PASS |
| Load | Normal load | 50 | 27ms | 0% | 32 | 15,493 | PASS |
| Stress | Overload | 300 | 129ms | 0% | 255 | 122,642 | PASS |
| Spike | Burst | 300 | 155ms | 0% | 117 | 24,630 | PASS |
| Soak | Endurance | 30 | 27ms | 0% | 23 | 44,111 | PASS |
| Breakpoint | Capacity | 500 | 106ms | 0% | 189 | 226,492 | PASS |
| Contention | Locking | 50 | 25ms† | 0% | 138 | 16,692 | PASS |
| Read vs Write (read) | Traffic profile | 30 | 29ms | 0% | 44 | ~8,200 | PASS |
| Read vs Write (write) | Traffic profile | 30 | 28ms | 0% | 44 | ~8,100 | PASS |
| Recovery | Resilience | 300 | 137ms | 0% | 103 | 38,250 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**All 10 tests PASS with 0% error rate.**

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Config:** 10 VUs, 30s duration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 75ms |
| p(90) | 69ms |
| Avg | 58ms |
| Median | 60ms |
| Max | 113ms |
| Error rate | 0% |
| Checks | 100% (2,831/2,831) |
| Total requests | 2,087 |
| RPS | 64 |
| Iterations | 149 |

**Conclusion:** Virtually identical to 1w and 2w at low load. Worker count doesn't matter at 10 VUs.

---

### A.2 Endpoint Benchmark

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario.

| Scenario | p(95) | Threshold | Result |
|----------|-------|-----------|--------|
| Light Reads | 67ms | <200ms | PASS |
| List Reads | 34ms | <500ms | PASS |
| Search & Filter | 56ms | <500ms | PASS |
| Writes | 65ms | <1000ms | PASS |
| Heavy Aggregations | 68ms | <1500ms | PASS |

- **Total requests:** 24,475
- **Checks:** 100% (24,474/24,474)
- **Error rate:** 0%

**Conclusion:** All scenarios pass. Marginally better than 1w/2w on list reads (34ms vs 41-65ms), possibly due to better read parallelism across workers.

---

## Phase B — Standard Test Types (Mixed Realistic Traffic)

### B.1 Load Test

**Config:** 0 → 50 VUs (2 min) → hold 50 (5 min) → ramp down (1 min).
**Thresholds:** p(95) < 500ms, p(99) < 1000ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 27ms |
| p(90) | 24ms |
| Avg | 16ms |
| Median | 15ms |
| Max | 86ms |
| Error rate | 0% |
| Total requests | 15,493 |
| RPS | 32 |
| Bookings | 1,906 |

**Conclusion:** Identical performance to 1w/2w. At 50 VUs, a single worker can handle the load.

---

### B.2 Stress Test

**Config:** 0 → 50 → 100 → 200 → 300 VUs over 8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

| Metric | Value |
|--------|-------|
| p(95) | **129ms** |
| p(90) | 105ms |
| Avg | 49ms |
| Median | 36ms |
| Max | 649ms |
| Error rate | 0% |
| Checks | 100% (122,641/122,641) |
| Total requests | 122,642 |
| RPS | **255** |
| Bookings | 13,871 success / 664 sold out |

**Best stress result across all configs.** 4w achieves the lowest p(95) (129ms) and highest RPS (255) at 300 VUs. The 4 event loops distribute the load effectively.

**Cross-config comparison:**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| 1w | 151ms | 251 | 0% |
| 2w | 529ms | 178 | 0.14% |
| 4w | **129ms** | **255** | 0% |

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 in 10s → hold 30s → drop to 10 → observe.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **155ms** |
| p(90) | 121ms |
| Avg | 51ms |
| Median | 32ms |
| Max | 310ms |
| Error rate | 0% |
| Checks | 100% (24,629/24,629) |
| Total requests | 24,630 |
| RPS | 117 |
| Bookings | 2,998 |

**Best spike result.** 4w has the lowest spike p(95) (155ms vs 658ms 2w, 525ms 1w) and lowest max (310ms vs 962ms 2w, 1441ms 1w). When 290 VUs arrive in 10 seconds, 4 event loops absorb the burst more evenly than 1 or 2.

**Conclusion:** The 4-worker config provides the best spike resilience, processing the burst with sub-200ms p(95) latency.

---

### B.4 Soak Test

**Config:** 30 VUs, 32 minutes.
**Thresholds:** p(95) < 700ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 27ms |
| p(90) | 24ms |
| Avg | 15ms |
| Median | 13ms |
| Max | 88ms |
| Error rate | 0% |
| Total requests | 44,111 |
| RPS | 23 |
| Bookings | 5,358 |
| Duration | 32 min |

**Conclusion:** Zero degradation. Flat latency for 32 minutes. Identical to 1w/2w — endurance is not a differentiator.

---

### B.5 Breakpoint Test

**Config:** ramping-arrival-rate, 10 → 500 iterations/s over 20 min. maxVUs = 500.
**Thresholds:** p(95) < 5000ms with abortOnFail.

| Metric | Value |
|--------|-------|
| p(95) | **106ms** |
| p(90) | 86ms |
| Avg | 36ms |
| Median | 17ms |
| Max | 1,132ms |
| Error rate | 0% |
| Checks | 100% (226,491/226,491) |
| Total requests | 226,492 |
| RPS | **189** |
| Peak VUs | **58** (of 500 max) |
| Dropped iterations | **8** |
| Bookings | 22,946 success / 4,375 sold out |
| Duration | **20 min (full run)** |

**Outstanding result.** The 4-worker config ran the full 20-minute breakpoint with:
- 0% errors
- Only 58 VUs needed (requests complete so fast K6 needs few VUs)
- Only 8 dropped iterations (effectively zero)
- p(95) of 106ms — the best of all configs

**Cross-config breakpoint comparison:**
| Workers | p(95) | RPS | Errors | Peak VUs | Dropped | Duration |
|---------|-------|-----|--------|----------|---------|----------|
| 1w | 192ms | 189 | 0% | 154 | 134 | 20 min (full) |
| 2w | 30,686ms | 42 | 6.7% | 500 | 69,521 | ~15 min |
| 4w | **106ms** | **189** | **0%** | **58** | **8** | **20 min (full)** |

The 4w config is the most efficient — it processes the same throughput (189 RPS) with fewer VUs (58 vs 154) and lower latency (106ms vs 192ms) than 1w.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking event_id=1, 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | **25ms** |
| Booking latency avg | 14ms |
| Booking latency median | 11ms |
| HTTP p(95) | 63ms |
| Max | 421ms |
| Error rate | 0% |
| Total requests | 16,692 |
| RPS | 138 |
| Bookings success | 283 |
| Sold out (409) | 8,062 |

**Best contention result.** Despite 4 workers contending for the same DB row, booking p(95) is 25ms — lower than both 1w (29ms) and 2w (33ms).

**Cross-config contention comparison:**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| 1w | 29ms | 283 | 8,050 |
| 2w | 33ms | 283 | 8,003 |
| 4w | **25ms** | 283 | 8,062 |

All three correctly produce exactly 283 bookings with zero deadlocks. The 4w config has the lowest contention latency, likely because the 1:1 CPU-to-worker ratio means each worker processes its lock acquisition without CPU contention.

---

### C.2 Read vs Write Test

**Config:** Two sequential scenarios at 30 VUs, 3 min each.

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 29ms | 28ms |
| Avg | 17ms | 16ms |
| Error rate | 0% | 0% |
| Bookings | 859 | 2,806 |

- **Combined RPS:** 44
- **Checks:** 100%

**Conclusion:** Best read/write parity across all configs. Write-heavy actually has marginally lower p(95) than read-heavy, suggesting write operations benefit from the parallel worker architecture.

---

### C.3 Recovery Test

**Config:** 30 VU baseline → spike to 300 VUs → drop to 30 → 4 min observation.
**Thresholds:** p(95) < 10,000ms, error rate < 30%.

| Metric | Value |
|--------|-------|
| p(95) | **137ms** |
| p(90) | 106ms |
| Avg | 43ms |
| Median | 25ms |
| Max | 329ms |
| Error rate | 0% |
| Checks | 100% (38,249/38,249) |
| Total requests | 38,250 |
| RPS | 103 |
| Bookings | 4,571 |

**Best recovery result.** 4w achieves the lowest recovery p(95) (137ms vs 465ms 2w, 521ms 1w). More workers means the spike load is distributed, and each worker recovers independently.

**Cross-config recovery comparison:**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| 1w | 521ms | 1,459ms | 93 | 0% |
| 2w | 465ms | 712ms | 86 | 0% |
| 4w | **137ms** | **329ms** | **103** | 0% |

---

## Comparison with Old Infrastructure (4 Workers)

| Test | Old Infra p(95) | New Infra p(95) | Old Errors | New Errors | Change |
|------|----------------|-----------------|------------|------------|--------|
| Baseline | 72-78ms | 75ms | 0% | 0% | Similar |
| Load | 30-31ms | 27ms | 0% | 0% | Similar |
| Stress | **1,691-1,895ms** | **129ms** | **1.4-2.0%** | **0%** | 13x lower latency! |
| Spike | 44ms-3,412ms | **155ms** | 0-2.6% | **0%** | Consistent now |
| Soak | 29-34ms | 27ms | 0% | 0% | Similar |
| Breakpoint | 31ms-1,890ms | **106ms** | 0-4.2% | **0%** | Consistent now |
| Recovery | 1,598-2,450ms | **137ms** | 1.2-1.4% | **0%** | 10-18x improvement |

**Old infrastructure:** API 2 CPU / 1 GB (0.5 CPU per worker!), pool_size=10/max_overflow=20 per worker (shared)
**New infrastructure:** API 4 CPU / 2 GB (1.0 CPU per worker), pool_size=15/max_overflow=7 per worker (88 total)

The stress test improvement (1.7-1.9s → 129ms, 13x) is the most dramatic. Under old infra, 4 workers shared 2 CPUs — each worker was CPU-starved, leading to high latency under load. With 1:1 CPU-to-worker ratio, each worker runs its event loop without CPU contention.

---

## Key Conclusions — 4 Uvicorn Workers (New Infrastructure)

### Performance Envelope

| Metric | Value |
|--------|-------|
| Comfortable capacity | 50 VUs / 32 RPS — p(95) 27ms, 0% errors |
| Stress capacity | 300 VUs / 255 RPS — p(95) 129ms, 0% errors |
| Spike survival | 300 VU burst — p(95) 155ms, 0% errors, fastest recovery |
| Sustained ceiling | 189 RPS for 20 min — p(95) 106ms, 0% errors, 58 VUs |
| Endurance | 32 min at 30 VUs — zero degradation |

### Why 4 Workers Wins
1. **Best stress performance:** Lowest p(95) (129ms) and highest RPS (255) at 300 VUs
2. **Best spike resilience:** 155ms p(95) during 300 VU burst — 4 event loops distribute sudden load
3. **Best breakpoint efficiency:** Same 189 RPS throughput as 1w, but with only 58 VUs (vs 154) and lower latency (106ms vs 192ms)
4. **Best recovery:** 137ms p(95) vs 465ms (2w) and 521ms (1w) — workers recover independently
5. **Best contention:** 25ms booking p(95) despite 4 processes competing for row locks
6. **Zero errors everywhere:** 100% clean across all 10 tests

### The 1:1 CPU-to-Worker Ratio
The key insight for the thesis: 4 workers with 4 CPUs (1:1 ratio) outperforms 1 worker with 4 CPUs. Although a single worker has access to the same CPU resources, it can only use one core for its event loop. The 4-worker config utilizes all 4 cores, distributing connection handling across independent processes.

### Where Workers Don't Help
At low concurrency (50 VUs or less), all three configs perform identically. The multi-worker advantage only appears under high concurrency (200+ VUs) where connection queuing and event loop saturation become factors.
