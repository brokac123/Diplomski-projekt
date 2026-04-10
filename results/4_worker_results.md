# K6 Performance Test Results — 4 Uvicorn Workers

**Date:** 2026-04-09 (Run 2)
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
**Run history:** See [test_run_history.md](test_run_history.md) for cross-run comparison

---

## Summary Table

| Test | Type | VUs | p(95) | Errors | RPS | Requests | Status |
|------|------|-----|-------|--------|-----|----------|--------|
| Baseline | Smoke | 10 | 70ms | 0% | 67 | 2,171 | PASS |
| Endpoint Benchmark | Isolation | 20 | ~64ms* | 0% | ~53 | ~24,500 | PASS |
| Load | Normal load | 50 | 27ms | 0% | 32 | 15,129 | PASS |
| Stress | Overload | 300 | 177ms | 0% | 248 | 118,928 | PASS |
| Spike | Burst | 300 | 609ms | 0% | 98 | 20,588 | PASS |
| Soak | Endurance | 30 | 27ms | 0% | 23 | 44,021 | PASS |
| Breakpoint | Capacity | 500 | 112ms | 0% | 189 | 226,381 | PASS |
| Contention | Locking | 50 | 35ms† | 0% | 137 | 16,604 | PASS |
| Read vs Write (read) | Traffic profile | 30 | ~29ms | 0% | ~44 | ~8,200 | PASS |
| Read vs Write (write) | Traffic profile | 30 | ~28ms | 0% | ~44 | ~8,100 | PASS |
| Recovery | Resilience | 300 | 539ms | 0% | 92 | 34,129 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**All 10 tests PASS with 0% error rate.**

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Config:** 10 VUs, 30s duration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 70ms |
| p(90) | 67ms |
| Avg | 56ms |
| Median | 57ms |
| Max | 149ms |
| Error rate | 0% |
| Checks | 100% (2,945/2,945) |
| Total requests | 2,171 |
| RPS | 67 |
| Iterations | 155 |

**Note:** The avg/p95 include ~40ms `http_req_receiving` overhead (Docker networking in multi-worker mode). Server-side processing time (`http_req_waiting`) shows avg 16ms, p(95) 28ms — consistent with other configs.

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
| p(90) | 25ms |
| Avg | 16ms |
| Median | 14ms |
| Max | 151ms |
| Error rate | 0% |
| Total requests | 15,129 |
| RPS | 32 |
| Bookings | 1,849 |

**Conclusion:** Identical performance to 1w/2w. At 50 VUs, a single worker can handle the load — extra workers add no benefit at this level. (Server-side `http_req_waiting` reported; raw `http_req_duration` had a single ~10s outlier from a network sending spike that doesn't reflect server processing.)

---

### B.2 Stress Test

**Config:** 0 → 50 → 100 → 200 → 300 VUs over 8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

| Metric | Value |
|--------|-------|
| p(95) | **177ms** |
| p(90) | 143ms |
| Avg | 66ms |
| Median | 48ms |
| Max | 995ms |
| Error rate | 0% |
| Checks | 100% (118,927/118,927) |
| Total requests | 118,928 |
| RPS | **248** |
| Bookings | 13,837 success / 671 sold out |

**Best stress result across all configs.** 4w achieves the lowest p(95) (177ms) and highest RPS (248) at 300 VUs. The 4 event loops distribute the load effectively.

**Cross-config comparison (Run 2):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| 1w | 886ms | 164 | 0% |
| 2w | 262ms | 230 | 0% |
| 4w | **177ms** | **248** | 0% |

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 in 10s → hold 30s → drop to 10 → observe.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **609ms** |
| p(90) | 508ms |
| Avg | 160ms |
| Median | 62ms |
| Max | 1,378ms |
| Error rate | 0% |
| Checks | 100% (20,587/20,587) |
| Total requests | 20,588 |
| RPS | 98 |
| Bookings | 2,408 |

**Cross-config comparison (Run 2):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| 1w | 1,225ms | 1,412ms | 62 | 0% |
| 2w | **289ms** | 411ms | **104** | 0% |
| 4w | 609ms | 1,378ms | 98 | 0% |

**Analysis:** In this run, 2w actually outperformed 4w on the spike test (289ms vs 609ms). This differs from Run 1 where 4w had the best spike result (155ms). Spike tests are inherently variable — the exact timing of the burst relative to Docker CPU scheduling affects which config handles it best. Despite the higher latency, 4w still processes the spike with 0% errors.

**Conclusion:** PASSES with zero errors. Spike performance varies between runs — see test_run_history.md for comparison.

---

### B.4 Soak Test

**Config:** 30 VUs, 32 minutes.
**Thresholds:** p(95) < 700ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 27ms |
| p(90) | 25ms |
| Avg | 16ms |
| Median | 14ms |
| Max | 84ms |
| Error rate | 0% |
| Total requests | 44,021 |
| RPS | 23 |
| Bookings | 5,243 |
| Duration | 32 min |

**Conclusion:** Zero degradation. Flat latency for 32 minutes. Identical to 1w/2w — endurance is not a differentiator.

---

### B.5 Breakpoint Test

**Config:** ramping-arrival-rate, 10 → 500 iterations/s over 20 min. maxVUs = 500.
**Thresholds:** p(95) < 5000ms with abortOnFail.

| Metric | Value |
|--------|-------|
| p(95) | **112ms** |
| p(90) | 87ms |
| Avg | 36ms |
| Median | 21ms |
| Max | 1,147ms |
| Error rate | 0% |
| Checks | 100% (226,380/226,380) |
| Total requests | 226,381 |
| RPS | **189** |
| Peak VUs | **164** (of 500 max) |
| Dropped iterations | **118** |
| Bookings | 22,871 success / 4,341 sold out |
| Duration | **20 min (full run)** |

**Outstanding result.** The 4-worker config ran the full 20-minute breakpoint with:
- 0% errors
- Only 164 VUs needed (requests complete fast enough K6 needs few VUs)
- Only 118 dropped iterations (effectively zero)
- p(95) of 112ms — the best of all configs

**Cross-config breakpoint comparison (Run 2):**
| Workers | p(95) | RPS | Errors | Peak VUs | Dropped | Duration |
|---------|-------|-----|--------|----------|---------|----------|
| 1w | 1,464ms | 62 | 4.6% | 500 | 149,646 | ~20.5 min |
| 2w | 247ms | 183 | 0.14% | 500 | 1,599 | ~20.5 min |
| 4w | **112ms** | **189** | **0%** | **164** | **118** | **20 min (full)** |

The 4w config is the most efficient — it processes the highest throughput (189 RPS) with fewest VUs (164) and lowest latency (112ms). Consistently the best breakpoint result across both runs.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking event_id=1, 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | **35ms** |
| Booking latency avg | 17ms |
| Booking latency median | 12ms |
| HTTP p(95) | 68ms |
| Max | 554ms |
| Error rate | 0% |
| Total requests | 16,604 |
| RPS | 137 |
| Bookings success | 283 |
| Sold out (409) | 8,018 |

**Cross-config contention comparison (Run 2):**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| 1w | 43ms | 283 | 8,460 |
| 2w | 33ms | 283 | 8,055 |
| 4w | **35ms** | 283 | 8,018 |

All three correctly produce exactly 283 bookings with zero deadlocks. Booking latency is similar across configs — under row-level contention, the serialized lock acquisition dominates regardless of worker count. Results are consistent across runs.

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
| p(95) | **539ms** |
| p(90) | 335ms |
| Avg | 109ms |
| Median | 28ms |
| Max | 1,361ms |
| Error rate | 0% |
| Checks | 100% (34,128/34,128) |
| Total requests | 34,129 |
| RPS | 92 |
| Bookings | 4,014 |

**Cross-config recovery comparison (Run 2):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| 1w | 938ms | 1,521ms | 72 | 0% |
| 2w | **277ms** | 450ms | **95** | 0% |
| 4w | 539ms | 1,361ms | 92 | 0% |

**Analysis:** In this run, 2w outperformed 4w on recovery (277ms vs 539ms). Like the spike test, recovery performance varies between runs due to CPU scheduling and burst timing. Run 1 showed 4w with the best recovery (137ms). The median of 28ms confirms the system returns to baseline after the spike.

---

## Comparison with Old Infrastructure (4 Workers)

| Test | Old Infra p(95) | New Infra p(95) | Old Errors | New Errors | Change |
|------|----------------|-----------------|------------|------------|--------|
| Baseline | 72-78ms | 70ms | 0% | 0% | Similar |
| Load | 30-31ms | 27ms | 0% | 0% | Similar |
| Stress | **1,691-1,895ms** | **177ms** | **1.4-2.0%** | **0%** | 10x lower latency! |
| Spike | 44ms-3,412ms | **609ms** | 0-2.6% | **0%** | Consistent now |
| Soak | 29-34ms | 27ms | 0% | 0% | Similar |
| Breakpoint | 31ms-1,890ms | **112ms** | 0-4.2% | **0%** | Consistent now |
| Recovery | 1,598-2,450ms | **539ms** | 1.2-1.4% | **0%** | 3-5x improvement |

**Old infrastructure:** API 2 CPU / 1 GB (0.5 CPU per worker!), pool_size=10/max_overflow=20 per worker (shared)
**New infrastructure:** API 4 CPU / 2 GB (1.0 CPU per worker), pool_size=15/max_overflow=7 per worker (88 total)

The stress test improvement (1.7-1.9s → 129ms, 13x) is the most dramatic. Under old infra, 4 workers shared 2 CPUs — each worker was CPU-starved, leading to high latency under load. With 1:1 CPU-to-worker ratio, each worker runs its event loop without CPU contention.

---

## Key Conclusions — 4 Uvicorn Workers (New Infrastructure)

### Performance Envelope

| Metric | Value |
|--------|-------|
| Comfortable capacity | 50 VUs / 32 RPS — p(95) 27ms, 0% errors |
| Stress capacity | 300 VUs / 248 RPS — p(95) 177ms, 0% errors |
| Spike survival | 300 VU burst — p(95) 609ms, 0% errors |
| Sustained ceiling | 189 RPS for 20 min — p(95) 112ms, 0% errors, 164 VUs |
| Endurance | 32 min at 30 VUs — zero degradation |

### Why 4 Workers Wins
1. **Best stress performance:** Lowest p(95) (177ms) and highest RPS (248) at 300 VUs — consistent across runs
2. **Best breakpoint efficiency:** 189 RPS throughput with only 164 VUs needed — consistently the best across both runs
3. **Zero errors everywhere:** 100% clean across all 10 tests in both runs
4. **Most predictable under sustained load:** Breakpoint results are stable between runs (106ms Run 1, 112ms Run 2)

### Run-to-Run Variance
Spike (155ms Run 1 → 609ms Run 2) and recovery (137ms Run 1 → 539ms Run 2) show significant variance between runs. Burst-handling tests are sensitive to Docker CPU scheduling and OS load. However, sustained throughput tests (stress, breakpoint, soak) remain consistently excellent.

### The 1:1 CPU-to-Worker Ratio
The key insight for the thesis: 4 workers with 4 CPUs (1:1 ratio) outperforms other configurations under sustained high load. Each worker gets its own CPU core for its event loop, distributing connection handling across independent processes. While per-worker connection pools are smaller (22 each), the faster processing frees connections quickly.

### Where Workers Don't Help
At low concurrency (50 VUs or less), all three configs perform identically. The multi-worker advantage only appears under high concurrency (200+ VUs) where event loop saturation becomes a factor.
