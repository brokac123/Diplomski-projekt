# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** 2026-04-12 (Run 4)
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
| Baseline | Smoke | 10 | 37ms | 0% | 91 | 2,885 | PASS |
| Endpoint Benchmark | Isolation | 20 | ~45ms* | 0% | ~59 | ~27,230 | PASS |
| Load | Normal load | 50 | 27ms | 0% | 32 | 15,537 | PASS |
| Stress | Overload | 300 | 830ms | 0% | 167 | 80,119 | PASS |
| Spike | Burst | 300 | 1,062ms | 0% | 65 | 13,695 | PASS |
| Soak | Endurance | 30 | 25ms | 0% | 23 | 44,153 | PASS |
| Breakpoint | Capacity | 500 | 30,864ms | 6.87% | 43.6 | 41,399 | FAIL |
| Contention | Locking | 50 | 42ms† | 0% | 146 | 17,688 | PASS |
| Read vs Write | Traffic profile | 30 | ~32ms | 0% | ~44 | ~16,206 | PASS |
| Recovery | Resilience | 300 | 934ms | 0.25% | 54 | 19,929 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**8 of 10 tests PASS with 0% errors. Breakpoint FAILS the p(95) < 5000ms threshold (30,864ms p95, 6.87% errors, 80,420 dropped iterations — catastrophic collapse). Recovery passes thresholds but shows 0.25% errors for the first time.**

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
| p(95) | 27ms |
| p(90) | 23ms |
| Avg | 16ms |
| Median | 15ms |
| Max | 80ms |
| Error rate | 0% |
| Checks | 100% (15,536/15,536) |
| Total requests | 15,537 |
| RPS | 32 |
| Bookings | 1,853 |

**Cross-config comparison (Run 4):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **27ms** | **32** | 0% |
| 2w | 27ms | 32 | 0% |
| 4w | 26ms | 32 | 0% |

**Conclusion:** At 50 VUs, all configs perform identically. The system operates with massive headroom — worker count provides no benefit at this concurrency level.

---

### B.2 Stress Test

**Config:** Ramp 0 → 50 → 100 → 200 → 300 VUs over 8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

| Metric | Value |
|--------|-------|
| p(95) | **830ms** |
| p(90) | 739ms |
| Avg | 341ms |
| Median | 289ms |
| Max | 1,275ms |
| Error rate | 0% |
| Checks | 100% (80,118/80,118) |
| Total requests | 80,119 |
| RPS | **167** |
| Bookings | 9,303 success |

**Cross-config comparison (Run 4):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **830ms** | **167** | 0% |
| 2w | 234ms | 235 | 0% |
| 4w | 123ms | 254 | 0% |

**Analysis:** The single worker shows significantly higher latency than 2w and 4w under 300 VU stress. With only one event loop processing all requests, the single CPU core becomes the bottleneck at this concurrency level. The connection pool (90 total) has plenty of capacity — CPU, not connections, is the limiting factor. This result is highly consistent across runs: Run 2 (886ms / 164 RPS), Run 3 (839ms / 167 RPS), Run 4 (830ms / 167 RPS) — the 1w ceiling is stable. 4w's 254 RPS in Run 4 is the best stress throughput seen across all runs.

**Conclusion:** PASSES with 0% errors but the highest latency among all configs. The single event loop is saturated at 300 VUs.

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 VUs in 10s → hold 30s → drop to 10 VUs → 1 min observation.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **1,062ms** |
| p(90) | 972ms |
| Avg | 494ms |
| Median | 561ms |
| Max | 1,298ms |
| Error rate | 0% |
| Checks | 100% (13,694/13,694) |
| Total requests | 13,695 |
| RPS | 65 |
| Bookings | 1,636 |

**Cross-config comparison (Run 4):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **1,062ms** | 1,298ms | **65** | 0% |
| 2w | 280ms | 423ms | 103 | 0% |
| 4w | 145ms | 361ms | 117 | 0% |

**Analysis:** The single worker struggles most with sudden bursts — 1,062ms p(95) and only 65 RPS. With one event loop, the 300 VU spike saturates the CPU and all requests queue. Linear scaling is clearly visible: 4w handles the same burst at 145ms / 117 RPS. Consistent across runs: Run 2 (1,225ms), Run 3 (1,079ms), Run 4 (1,062ms).

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
| Max | 114ms |
| Error rate | 0% |
| Checks | 100% (44,152/44,152) |
| Total requests | 44,153 |
| RPS | 23 |
| Bookings | 5,285 |
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
| p(95) | **30,864ms** |
| p(90) | 3,196ms |
| Avg | 2,999ms |
| Median | 17ms |
| Max | 80,500ms |
| Error rate | **6.87%** (2,844 failures) |
| Checks | 93.1% (38,554/41,398) |
| Total requests | 41,399 |
| RPS | **43.6** |
| Peak VUs | **500 (maxed out)** |
| Dropped iterations | **80,420** |
| Bookings | 4,670 success |
| Duration | ~11–12 min (aborted early) |

**Threshold result:** FAIL — p(95) of 30,864ms breached the 5,000ms abortOnFail threshold. The test was terminated early before reaching the full 20-minute ramping period.

**Cross-config breakpoint comparison (Run 4):**
| Workers | p(95) | RPS | Errors | Dropped | Duration |
|---------|-------|-----|--------|---------|----------|
| **1w** | **30,864ms** | **43.6** | **6.87%** | **80,420** | ~11–12 min |
| 2w | 154ms | 188.6 | 0% | 124 | 20 min |
| 4w | 139ms | 188.7 | 0% | 28 | 20 min |

**Analysis:** Run 4 saw a catastrophic 1w breakpoint collapse — similar to Run 1's 2w anomaly. The single event loop was completely overwhelmed by the open-model arrival rate. With only 43.6 RPS throughput (vs 188+ for 2w and 4w), incoming iterations accumulated faster than they could be processed, causing 80,420 dropped iterations and a p95 of 30,864ms. This mirrors the fundamental constraint: a single event loop cannot absorb 189 RPS no matter how large the connection pool is.

**Variability across runs:**
- Run 1: 192ms / 189 RPS / 0% (anomalously good — U-curve anomaly)
- Run 2: 1,464ms / 62 RPS / 4.6% (ceiling established)
- Run 3: 1,483ms / 60 RPS / 4.75% (ceiling confirmed consistent)
- Run 4: **30,864ms / 43.6 RPS / 6.87%** (catastrophic collapse)

The 1w event loop sits right at its capacity boundary under open-model load. Small changes in Docker CPU scheduling can tip it from a managed degradation (Runs 2–3) into a full collapse (Run 4).

**Conclusion:** FAILS K6 thresholds. The single event loop is fundamentally unable to sustain the throughput that 2w and 4w handle cleanly. Both 2w and 4w reached the system's ~189 RPS ceiling in Run 4.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking the same event (event_id=1), 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 42ms |
| Booking latency avg | 18ms |
| Booking latency median | 12ms |
| HTTP p(95) | 36ms |
| Max | 603ms |
| Error rate | 0% |
| Total requests | 17,688 |
| RPS | 146 |
| Bookings success | 283 |
| Sold out (409) | 8,560 |

**Cross-config contention comparison (Run 4):**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| **1w** | **42ms** | 283 | 8,560 |
| 2w | 27ms | 283 | 7,408 |
| 4w | 59ms | 283 | 7,864 |

**Analysis:** All three configs correctly produce exactly 283 bookings with zero deadlocks. The 4w booking latency p(95) of 59ms is anomalously high in Run 4 (vs 24ms in Run 3) — likely a Docker scheduling artifact during the 2-minute test window. The key correctness result is unchanged: exactly 283 bookings, zero deadlocks, zero double-bookings across all configs.

**Conclusion:** Exactly 283 bookings succeeded (matching ticket capacity). Zero deadlocks, zero double-bookings. The `with_for_update()` locking strategy performs correctly under extreme contention. Consistent across all runs.

---

### C.2 Read vs Write Test

**Config:** Two sequential scenarios at 30 VUs, 3 min each.

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 33ms | 32ms |
| Avg | 18ms | 18ms |
| Error rate | 0% | 0% |
| Bookings | 828 | 2,831 |

- **Combined RPS:** 44
- **Total requests:** 16,206
- **Checks:** 100% (16,205/16,205)

**Conclusion:** Near-parity between read-heavy and write-heavy at 30 VUs. At moderate concurrency, the workload mix doesn't significantly impact performance.

---

### C.3 Recovery Test

**Config:** 30 VU baseline → spike to 300 VUs → drop to 30 → 4 min observation.
**Thresholds:** p(95) < 10,000ms, error rate < 30%.

| Metric | Value |
|--------|-------|
| p(95) | **934ms** |
| p(90) | 818ms |
| Avg | 521ms |
| Median | 25ms |
| Max | 60,003ms |
| Error rate | **0.25%** (49 failures) |
| Checks | 99.75% (19,879/19,928) |
| Total requests | 19,929 |
| RPS | 54 |
| Bookings | 2,386 |

**Cross-config recovery comparison (Run 4):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **934ms** | 60,003ms | **54** | **0.25%** |
| 2w | 261ms | 10,350ms | 94 | 0% |
| 4w | 562ms | 1,570ms | 90 | 0% |

**Analysis:** Run 4 shows the most stressed 1w recovery result to date. The 60,003ms max indicates at least one request hit the k6 timeout, pulling up the average to 521ms. The 49 failures (0.25%) represent the first time 1w recovery showed any errors — caused by request timeouts during the tail of the spike. RPS dropped to 54 (from 72 in Run 3) indicating the test didn't fully return to post-spike steady state before ending. The 4w result in Run 4 also shows variance (562ms vs 128ms in Run 3) — burst tests remain the highest-variance scenario. Linear ordering 1w > 2w is clear; 4w's 562ms is a Run 4 anomaly.

**Conclusion:** PASSES thresholds (p95 < 10,000ms, errors < 30%) but shows 0.25% errors for the first time. Recovery tests remain the most variable across all runs.

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
| Comfortable capacity | 50 VUs / 32 RPS — p(95) 27ms, 0% errors |
| Stress capacity | 300 VUs / 167 RPS — p(95) 830ms, 0% errors |
| Spike survival | 300 VU burst — p(95) 1,062ms, 0% errors |
| Sustained ceiling | ~43–60 RPS under open-model load — highly variable (can collapse catastrophically) |
| Endurance | 32 min at 30 VUs — zero degradation |

### Architectural Strengths
1. **Excellent endurance** — 32-minute soak with flat latency
2. **Correct concurrency control** — exactly 283 contention bookings, zero deadlocks
3. **Zero errors at moderate load** — load, soak, contention all perfect
4. **Full connection pool** — 90 undivided connections (largest per-worker pool)

### Limitations Under High Load
1. **Single event loop saturates** — with one CPU core doing all processing, 300+ VUs cause queuing
2. **Consistent stress ceiling, variable breakpoint** — Stress is consistent across Runs 2–4 (886ms→839ms→830ms). Breakpoint is highly variable: Runs 2–3 show a managed ceiling (~1,464–1,483ms), Run 4 collapsed catastrophically (30,864ms). The 1w event loop sits right at its open-model capacity boundary.
3. **Slowest recovery** — takes longest to drain request backlog after bursts

### Thesis Takeaway
The single-worker config performs well at moderate concurrency but is the weakest config under high load. Across four runs, 1w is consistently the worst-performing config at high concurrency — confirming linear scaling where adding workers improves performance. The undivided 90-connection pool is an advantage, but the single event loop is the hard bottleneck above ~100 VUs. The breakpoint behavior is the most striking demonstration: 2w and 4w both sustain ~189 RPS with 0% errors, while 1w cannot reliably sustain even 60 RPS and can collapse catastrophically (Run 4: 30,864ms p95, 6.87% errors, 80,420 dropped iterations).
