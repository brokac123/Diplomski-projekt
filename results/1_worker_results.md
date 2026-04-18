# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** 2026-04-18 (Run 6)
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
| Baseline | Smoke | 10 | 39ms | 0% | 91 | 2,885 | PASS |
| Endpoint Benchmark | Isolation | 20 | ~45ms* | 0% | ~59 | ~27,000 | PASS |
| Load | Normal load | 50 | 24ms | 0% | 32 | 15,478 | PASS |
| Stress | Overload | 300 | 854ms | 0% | 168 | 80,748 | PASS |
| Spike | Burst | 300 | 1,235ms | 0% | 55 | 11,557 | PASS |
| Soak | Endurance | 30 | 25ms | 0% | 23 | 44,049 | PASS |
| Breakpoint | Capacity | 500 | 795ms | 3.48% | 71 | 87,137 | PASS* |
| Contention | Locking | 50 | 40ms† | 0% | 145 | 17,596 | PASS |
| Read vs Write | Traffic profile | 30 | ~32ms | 0% | ~44 | ~16,235 | PASS |
| Recovery | Resilience | 300 | 987ms | 0% | 73 | 27,040 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**9 of 10 tests PASS with 0% errors. Breakpoint passes the K6 p(95) < 5000ms threshold (795ms) but shows 3.48% errors and 138,953 dropped iterations — moderate collapse. The event loop is at its capacity boundary under open-model load.**

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 39ms |
| p(90) | 25ms |
| Avg | 16ms |
| Median | 12ms |
| Max | 136ms |
| Error rate | 0% |
| Checks | 100% (3,914/3,914) |
| Total requests | 2,885 |
| RPS | 91 |

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

- **Total requests:** 27,230
- **Checks:** 100% (27,229/27,229)
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
| p(95) | 24ms |
| p(90) | 21ms |
| Avg | 13ms |
| Median | 12ms |
| Max | 125ms |
| Error rate | 0% |
| Checks | 100% (15,477/15,477) |
| Total requests | 15,478 |
| RPS | 32 |
| Bookings | 1,851 |

**Cross-config comparison (Run 6):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **24ms** | **32** | 0% |
| 2w | 24ms | 32 | 0% |
| 4w | 25ms | 32 | 0% |

**Conclusion:** At 50 VUs, all configs perform identically. The system operates with massive headroom — worker count provides no benefit at this concurrency level.

---

### B.2 Stress Test

**Config:** Ramp 0 → 50 → 100 → 200 → 300 VUs over 8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

| Metric | Value |
|--------|-------|
| p(95) | **854ms** |
| p(90) | 762ms |
| Avg | 335ms |
| Median | 255ms |
| Max | 3,733ms |
| Error rate | 0% |
| Checks | 100% (80,747/80,747) |
| Total requests | 80,748 |
| RPS | **168** |
| Bookings | 9,413 success |

**Cross-config comparison (Run 6):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **854ms** | **168** | 0% |
| 2w | 248ms | 232 | 0% |
| 4w | 141ms | 254 | 0% |

**Analysis:** The single worker shows significantly higher latency than 2w and 4w under 300 VU stress. With only one event loop processing all requests, the single CPU core becomes the bottleneck at this concurrency level. The connection pool (90 total) has plenty of capacity — CPU, not connections, is the limiting factor. This result is highly consistent across runs: Run 2 (886ms / 164 RPS), Run 3 (839ms / 167 RPS), Run 4 (830ms / 167 RPS), Run 5 (804ms / 174 RPS), Run 6 (854ms / 168 RPS) — the 1w ceiling is stable across all runs.

**Conclusion:** PASSES with 0% errors but the highest latency among all configs. The single event loop is saturated at 300 VUs.

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 VUs in 10s → hold 30s → drop to 10 VUs → 1 min observation.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **1,235ms** |
| p(90) | 1,199ms |
| Avg | 680ms |
| Median | 949ms |
| Max | 1,512ms |
| Error rate | 0% |
| Checks | 100% (11,556/11,556) |
| Total requests | 11,557 |
| RPS | 55 |
| Bookings | 1,391 |

**Cross-config comparison (Run 6):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **1,235ms** | 1,512ms | **55** | 0% |
| 2w | 297ms | 494ms | 103 | 0% |
| 4w | 154ms | 369ms | 118 | 0% |

**Analysis:** The single worker struggles most with sudden bursts — 1,235ms p(95) and only 55 RPS. With one event loop, the 300 VU spike saturates the CPU and all requests queue. Linear scaling is clearly visible: 4w handles the same burst at 154ms / 118 RPS. Consistent across runs: Run 2 (1,225ms), Run 3 (1,079ms), Run 4 (1,062ms), Run 5 (845ms), Run 6 (1,235ms).

**Conclusion:** PASSES with 0% errors but highest spike latency among all configs.

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
| Max | 271ms |
| Error rate | 0% |
| Checks | 100% (44,048/44,048) |
| Total requests | 44,049 |
| RPS | 23 |
| Bookings | 5,291 |
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
| p(95) | **795ms** |
| p(90) | 199ms |
| Avg | 2,159ms |
| Median | 17ms |
| Max | 60,009ms |
| Error rate | **3.48%** (3,029 failures) |
| Checks | 96.5% (84,107/87,136) |
| Total requests | 87,137 |
| RPS | **71** |
| Peak VUs | 500 |
| Dropped iterations | **138,953** |
| Bookings | 9,916 success |
| Duration | ~20.5 min (ran to completion) |

**Threshold result:** PASS* — p(95) of 795ms is below the 5,000ms abortOnFail threshold, so the test ran to completion. However, 3.48% error rate and 138,953 dropped iterations indicate the event loop is under severe stress.

**Cross-config breakpoint comparison (Run 6):**
| Workers | p(95) | RPS | Errors | Dropped | Duration |
|---------|-------|-----|--------|---------|----------|
| **1w** | **795ms** | **71** | **3.48%** | **138,953** | ~20.5 min |
| 2w | 149ms | 189 | 0% | 189 | 20 min |
| 4w | 51ms | 189 | 0% | 8 | 20 min |

**Analysis:** Run 6 shows moderate 1w collapse — nearly identical to Run 5 (814ms / 3.36%). The bimodal distribution (median=17ms, avg=2,159ms) shows most requests either complete quickly or time out. RPS of 71 (vs 189 for 4w) confirms the 1w ceiling. 4w and 2w both hit ~189 RPS with 0% errors in this run.

**Variability across runs:**
- Run 1: 192ms / 189 RPS / 0% (anomalously good — U-curve anomaly)
- Run 2: 1,464ms / 62 RPS / 4.6% (stable degraded ceiling)
- Run 3: 1,483ms / 60 RPS / 4.75% (ceiling confirmed consistent)
- Run 4: **30,864ms / 43.6 RPS / 6.87%** (catastrophic collapse, aborted early)
- Run 5: **814ms / 72.9 RPS / 3.36%** (moderate collapse, ran to completion)
- Run 6: **795ms / 71 RPS / 3.48%** (moderate collapse — consistent with Run 5)

Three distinct regimes observed: stable degraded (~1,480ms, Runs 2–3), moderate collapse (~795–814ms p95, Runs 5–6), catastrophic collapse (30,864ms, Run 4). The 1w event loop sits right at its capacity boundary — Docker CPU scheduling determines which regime occurs.

**Conclusion:** PASSES K6 thresholds in Run 5 but shows significant degradation. The single event loop is fundamentally unable to sustain the throughput that 4w handles cleanly (189 RPS). 1w behavior under open-model load is inherently unpredictable.

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
| Max | 533ms |
| Error rate | 0% |
| Total requests | 17,596 |
| RPS | 145 |
| Bookings success | 283 |
| Sold out (409) | 8,514 |

**Cross-config contention comparison (Run 6):**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| **1w** | **40ms** | 283 | 8,514 |
| 2w | 27ms | 283 | 8,085 |
| 4w | 23ms | 283 | 8,119 |

**Analysis:** All three configs correctly produce exactly 283 bookings with zero deadlocks. The 283-booking invariant has held across all 6 runs and all 3 configs without exception — proving transaction isolation is preserved regardless of worker count.

**Conclusion:** Exactly 283 bookings succeeded (matching ticket capacity). Zero deadlocks, zero double-bookings. The `with_for_update()` locking strategy performs correctly under extreme contention. Consistent across all runs.

---

### C.2 Read vs Write Test

**Config:** Two sequential scenarios at 30 VUs, 3 min each.

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 33ms | 31ms |
| Avg | 18ms | 18ms |
| Error rate | 0% | 0% |
| Bookings | 776 | 2,826 |

- **Combined RPS:** 44
- **Total requests:** 16,235
- **Checks:** 100% (16,234/16,234)

**Conclusion:** Near-parity between read-heavy and write-heavy at 30 VUs. At moderate concurrency, the workload mix doesn't significantly impact performance.

---

### C.3 Recovery Test

**Config:** 30 VU baseline → spike to 300 VUs → drop to 30 → 4 min observation.
**Thresholds:** p(95) < 10,000ms, error rate < 30%.

| Metric | Value |
|--------|-------|
| p(95) | **987ms** |
| p(90) | 835ms |
| Avg | 269ms |
| Median | 29ms |
| Max | 1,251ms |
| Error rate | 0% |
| Checks | 100% (27,039/27,039) |
| Total requests | 27,040 |
| RPS | 73 |
| Bookings | 3,241 |

**Cross-config recovery comparison (Run 6):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **987ms** | 1,251ms | **73** | 0% |
| 2w | 280ms | 498ms | 95 | 0% |
| 4w | 146ms | 408ms | 103 | 0% |

**Analysis:** Run 6 confirms clear linear ordering in recovery: 4w (146ms) < 2w (280ms) < 1w (987ms), all 0% errors — identical pattern to Run 5. The 1w result (987ms) is consistent with the ~960–987ms range seen in Runs 3 and 6. Linear scaling is clearly visible in recovery behavior.

**Conclusion:** PASSES thresholds with 0% errors. Linear ordering holds for the second consecutive run.

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
| Comfortable capacity | 50 VUs / 32 RPS — p(95) 24ms, 0% errors |
| Stress capacity | 300 VUs / 168 RPS — p(95) 854ms, 0% errors |
| Spike survival | 300 VU burst — p(95) 1,235ms, 0% errors |
| Sustained ceiling | ~43–189 RPS under open-model load — highly variable (ranges from moderate degradation to catastrophic collapse) |
| Endurance | 32 min at 30 VUs — zero degradation |

### Architectural Strengths
1. **Excellent endurance** — 32-minute soak with flat latency
2. **Correct concurrency control** — exactly 283 contention bookings, zero deadlocks
3. **Zero errors at moderate load** — load, soak, contention all perfect
4. **Full connection pool** — 90 undivided connections (largest per-worker pool)

### Limitations Under High Load
1. **Single event loop saturates** — with one CPU core doing all processing, 300+ VUs cause queuing
2. **Consistent stress ceiling, variable breakpoint** — Stress is consistent across Runs 2–6 (886ms→839ms→830ms→804ms→854ms). Breakpoint is highly variable: three distinct regimes observed — stable degraded (Runs 2–3, ~1,480ms), moderate collapse (Runs 5–6, ~795–814ms p95 but avg=2,000ms+, 136–139K dropped), catastrophic collapse (Run 4, 30,864ms, aborted early).
3. **Slowest recovery** — takes longest to drain request backlog after bursts

### Thesis Takeaway
The single-worker config performs well at moderate concurrency but is the weakest config under high load. Across six runs, 1w is consistently the worst-performing config at high concurrency — confirming linear scaling where adding workers improves performance. The undivided 90-connection pool is an advantage, but the single event loop is the hard bottleneck above ~100 VUs. The breakpoint behavior is the most striking demonstration: 4w sustains ~189 RPS with 0% errors across all 6 runs, while 1w cannot reliably sustain even 73 RPS and can collapse catastrophically (Run 4: 30,864ms p95, 6.87% errors, 80,420 dropped iterations).
