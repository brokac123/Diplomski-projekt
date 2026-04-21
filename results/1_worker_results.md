# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** 2026-04-21 (Run 9)
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
| Baseline | Smoke | 10 | 33ms | 0% | 92 | 2,913 | PASS |
| Endpoint Benchmark | Isolation | 20 | ~41ms* | 0% | ~59 | ~27,335 | PASS |
| Load | Normal load | 50 | 27ms | 0% | 32 | 15,440 | PASS |
| Stress | Overload | 300 | 1,634ms | 0% | 120 | 57,829 | FAIL |
| Spike | Burst | 300 | 1,933ms | 0% | 44 | 9,199 | PASS |
| Soak | Endurance | 30 | 25ms | 0% | 23 | 44,228 | PASS |
| Breakpoint | Capacity | 500 | 888ms | 3.55% | 69 | 85,312 | PASS* |
| Contention | Locking | 50 | 41ms† | 0% | 146 | 17,592 | PASS |
| Read vs Write | Traffic profile | 30 | ~32ms | 0% | ~43 | ~16,112 | PASS |
| Recovery | Resilience | 300 | 778ms | 0% | 75 | 27,620 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**8 of 10 tests PASS with 0% errors. Stress FAILS the 1,500ms threshold (1,634ms p95) — genuine CPU saturation confirmed by clean 2w and 4w results (unlike Run 7's WSL2-wide degradation). Spike passes barely (1,933ms < 2,000ms threshold). Breakpoint passes K6 threshold (p95=888ms < 5,000ms, ran to full ~20.5 min) but shows 3.55% errors and 140,900 dropped iterations (PASS*) — moderate collapse regime. Run 9 is the second stress threshold failure across 9 runs; Run 7 was WSL2 fragmentation, Run 9 is the genuine 1w CPU ceiling at 300 VUs.**

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 33ms |
| p(90) | 25ms |
| Avg | 15ms |
| Median | 13ms |
| Max | 91ms |
| Error rate | 0% |
| Checks | 100% (3,952/3,952) |
| Total requests | 2,913 |
| RPS | 92 |

**Conclusion:** All endpoints healthy. The system handles 10 concurrent users with sub-40ms p(95) latency.

---

### A.2 Endpoint Benchmark

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario.
**All 5 scenarios PASS** — including heavy aggregations, which previously failed under old infrastructure.

| Scenario | Endpoints | p(95) | Threshold | Result |
|----------|-----------|-------|-----------|--------|
| Light Reads | GET /health, /users/{id}, /events/{id}, /bookings/{id} | ~36ms | <200ms | PASS |
| List Reads | GET /users/, /events/, /bookings/ | ~63ms | <500ms | PASS |
| Search & Filter | GET /events/search, /events/upcoming, /users/{id}/bookings, /events/{id}/bookings | ~22ms | <500ms | PASS |
| Writes | POST /bookings/, PATCH /bookings/{id}/cancel | ~46ms | <1000ms | PASS |
| Heavy Aggregations | GET /events/{id}/stats, /events/popular, /stats | ~30ms | <1500ms | PASS |

- **Total requests:** 27,335
- **Checks:** 100%
- **Error rate:** 0%
- **Overall p(95):** 41ms

**Key improvement:** Heavy aggregations p(95) dropped from 60,231ms (old infra) to ~30ms. The increased shared_buffers (512MB) and effective_cache_size (1GB) enable PostgreSQL to cache more data and choose index scans over sequential scans.

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
| Median | 14ms |
| Max | 97ms |
| Error rate | 0% |
| Checks | 100% (15,439/15,439) |
| Total requests | 15,440 |
| RPS | 32 |
| Bookings | 1,828 |

**Cross-config comparison (Run 8):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **27ms** | **32** | 0% |
| 2w | 26ms | 32 | 0% |
| 4w | 24ms | 32 | 0% |

**Conclusion:** At 50 VUs, all configs perform identically. The system operates with massive headroom — worker count provides no benefit at this concurrency level.

---

### B.2 Stress Test

**Config:** Ramp 0 → 50 → 100 → 200 → 300 VUs over 8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

| Metric | Value |
|--------|-------|
| p(95) | **1,634ms** |
| p(90) | 1,489ms |
| Avg | 667ms |
| Median | ~530ms |
| Max | ~1,800ms |
| Error rate | 0% |
| Checks | 100% (57,828/57,828) |
| Total requests | 57,829 |
| RPS | **120** |
| Bookings | 6,889 success |

**Cross-config comparison (Run 9):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **1,634ms ❌** | **120** | 0% |
| 2w | 388ms | 205 | 0% |
| 4w | 132ms | 255 | 0% |

**Analysis:** The single worker shows significantly higher latency than 2w and 4w under 300 VU stress. With only one event loop processing all requests, the single CPU core becomes the bottleneck at this concurrency level. Run 9 produced 1,634ms p95 — exceeding the 1,500ms threshold. 2w and 4w are completely clean (388ms and 132ms respectively), confirming this is genuine 1w CPU saturation and not a host-level anomaly (unlike Run 7's WSL2 fragmentation which degraded all configs). Across runs: Run 2 (886ms / 164 RPS), Run 3 (839ms / 167 RPS), Run 4 (830ms / 167 RPS), Run 5 (804ms / 174 RPS), Run 6 (854ms / 168 RPS), Run 7 (1,616ms / 120 RPS — WSL2 anomaly), Run 8 (740ms / 173 RPS), Run 9 (1,634ms / 120 RPS — genuine CPU saturation) — out of 9 runs, 1w stress has failed the threshold twice.

**Conclusion:** FAILS p(95) threshold (1,634ms > 1,500ms). Linear scaling ordering maintained: 4w > 2w > 1w clearly visible.

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 VUs in 10s → hold 30s → drop to 10 VUs → 1 min observation.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **1,933ms** |
| p(90) | 1,886ms |
| Avg | 989ms |
| Median | ~800ms |
| Max | ~2,100ms |
| Error rate | 0% |
| Checks | 100% (9,198/9,198) |
| Total requests | 9,199 |
| RPS | 44 |
| Bookings | 1,156 |

**Cross-config comparison (Run 9):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **1,933ms** | ~2,100ms | **44** | 0% |
| 2w | 467ms | ~550ms | 87 | 0% |
| 4w | 173ms | ~400ms | 116 | 0% |

**Analysis:** The single worker struggles most with sudden bursts — 1,933ms p(95) and only 44 RPS. Linear scaling is clearly visible: 4w handles the same burst at 173ms / 116 RPS. Consistent across runs: Run 2 (1,225ms), Run 3 (1,079ms), Run 4 (1,062ms), Run 5 (845ms), Run 6 (1,235ms), Run 7 (1,923ms), Run 8 (890ms), Run 9 (1,933ms).

**Conclusion:** PASSES threshold (1,933ms < 2,000ms — barely). 0% errors but highest spike latency among all configs.

---

### B.4 Soak Test

**Config:** 30 VUs, 32 minutes steady state.
**Thresholds:** p(95) < 700ms, error rate < 1%.

| Metric | Value |
|--------|-------|
| p(95) | 25ms |
| p(90) | 23ms |
| Avg | 15ms |
| Median | 13ms |
| Max | 72ms |
| Error rate | 0% |
| Checks | 100% (44,227/44,227) |
| Total requests | 44,228 |
| RPS | 23 |
| Bookings | 5,241 |
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
| p(95) | **888ms** |
| p(90) | ~400ms |
| Avg | 2,250ms |
| Median | 17ms |
| Max | 60,016ms |
| Error rate | **3.55%** (3,026 failures) |
| Checks | 96.45% (82,286/85,312) |
| Total requests | 85,312 |
| RPS | **69** |
| Peak VUs | 500 |
| Dropped iterations | **140,900** |
| Bookings | 9,848 success |
| Duration | ~20.5 min (full run) |

**Threshold result:** PASS* — p(95) of 888ms is within the 5,000ms abortOnFail threshold. The test ran to full completion (~20.5 min). However, 3.55% error rate and 140,900 dropped iterations indicate moderate collapse — the event loop could not sustain the arrival rate and began timing out requests.

**Cross-config breakpoint comparison (Run 9):**
| Workers | p(95) | RPS | Errors | Dropped | Duration |
|---------|-------|-----|--------|---------|----------|
| **1w** | **888ms** | **69** | **3.55%** | **140,900** | ~20.5 min (degraded) |
| 2w | 1,138ms | 140 | 0.57% | 53,778 | ~20.5 min (degraded) |
| 4w | 96ms | 189 | 0% | 18 | 20 min (clean, 30s early) |

**Analysis:** Run 9 shows 1w in moderate collapse — the bimodal distribution (median=17ms, avg=2,250ms) is characteristic of a system where most requests time out while a fast minority complete. The 140,900 dropped iterations confirm the system was severely under-provisioned for the offered arrival rate. Notably, Run 9 also saw 2w in a degraded state (1,138ms / 140 RPS / 0.57% errors), while 4w was the strongest breakpoint result ever (96ms / 189 RPS / 0% errors / completed 30s early).

**Variability across runs:**
- Run 1: 192ms / 189 RPS / 0% (anomalously good — U-curve anomaly)
- Run 2: 1,464ms / 62 RPS / 4.6% (stable degraded ceiling)
- Run 3: 1,483ms / 60 RPS / 4.75% (ceiling confirmed consistent)
- Run 4: **30,864ms / 43.6 RPS / 6.87%** (catastrophic collapse, aborted early)
- Run 5: **814ms / 72.9 RPS / 3.36%** (moderate collapse, ran to completion)
- Run 6: **795ms / 71 RPS / 3.48%** (moderate collapse — consistent with Run 5)
- Run 7: **31,348ms / 47.9 RPS / 4.64%** (catastrophic collapse — aborted at ~14.7 min, WSL2 memory anomaly)
- Run 8: **389ms / 71.5 RPS / 3.43%** (moderate collapse — ran to full completion)
- Run 9: **888ms / 69 RPS / 3.55%** (moderate collapse — consistent with Runs 5, 6, and 8)

Three distinct regimes confirmed: stable degraded (~1,480ms, Runs 2–3), moderate collapse (Runs 5–6, 8, and 9 — ~69–73 RPS, 3.4–4.75% errors), catastrophic collapse (Runs 4 and 7 — 30,000ms+). The moderate collapse regime is the normal 1w breakpoint behavior across Runs 5–6, 8, and 9.

**Conclusion:** K6 PASSES threshold (888ms < 5,000ms, no abort). However, 3.55% error rate and 140,900 dropped iterations confirm moderate collapse. 1w breakpoint ceiling is ~69–73 RPS under normal conditions. The single event loop is fundamentally unable to sustain the throughput that 4w handles cleanly (189 RPS).

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking the same event (event_id=1), 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 41ms |
| Booking latency avg | 18ms |
| Booking latency median | 12ms |
| HTTP p(95) | 36ms |
| Max | 548ms |
| Error rate | 0% |
| Total requests | 17,592 |
| RPS | 146 |
| Bookings success | 283 |
| Sold out (409) | 8,512 |

**Cross-config contention comparison (Run 8):**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| **1w** | **41ms** | 283 | 8,512 |
| 2w | 39ms | 283 | 7,977 |
| 4w | 29ms | 283 | 8,066 |

**Analysis:** All three configs correctly produce exactly 283 bookings with zero deadlocks. The 283-booking invariant has held across all 8 runs and all 3 configs without exception — proving transaction isolation is preserved regardless of worker count.

**Conclusion:** Exactly 283 bookings succeeded (matching ticket capacity). Zero deadlocks, zero double-bookings. The `with_for_update()` locking strategy performs correctly under extreme contention. Consistent across all runs.

---

### C.2 Read vs Write Test

**Config:** Two sequential scenarios at 30 VUs, 3 min each.

| Metric | Read-heavy (90R/10W) | Write-heavy (40R/60W) |
|--------|---------------------|----------------------|
| p(95) | 32ms | 32ms |
| Avg | 18ms | 18ms |
| Error rate | 0% | 0% |
| Bookings | 825 | 2,815 |

- **Combined RPS:** 43
- **Total requests:** 16,112
- **Checks:** 100%

**Conclusion:** Near-parity between read-heavy and write-heavy at 30 VUs. At moderate concurrency, the workload mix doesn't significantly impact performance.

---

### C.3 Recovery Test

**Config:** 30 VU baseline → spike to 300 VUs → drop to 30 → 4 min observation.
**Thresholds:** p(95) < 10,000ms, error rate < 30%.

| Metric | Value |
|--------|-------|
| p(95) | **778ms** |
| p(90) | 723ms |
| Avg | 253ms |
| Median | 30ms |
| Max | 1,199ms |
| Error rate | 0% |
| Checks | 100% (27,619/27,619) |
| Total requests | 27,620 |
| RPS | 75 |
| Bookings | 3,398 |

**Cross-config recovery comparison (Run 9):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **778ms** | 1,199ms | **75** | 0% |
| 2w | 451ms | 684ms | 85 | 0% |
| 4w | 124ms | 312ms | 104 | 0% |

**Analysis:** Run 9 shows clear linear ordering in recovery: 4w (124ms) < 2w (451ms) < 1w (778ms), all 0% errors. The 1w result (778ms) is in normal range. Linear scaling clearly visible in recovery behavior.

**Conclusion:** PASSES thresholds with 0% errors. Linear ordering confirmed for the ninth consecutive run.

---

## Comparison with Old Infrastructure

| Test | Old Infra p(95) | New Infra p(95) | Old Errors | New Errors | Improvement |
|------|----------------|-----------------|------------|------------|-------------|
| Baseline | 45-62ms | 33ms | 0% | 0% | Similar |
| Load | 29-34ms | 27ms | 0% | 0% | Similar |
| Stress | 353-457ms | **740ms** | 0.5-1.5% | **0%** | Higher latency but zero errors |
| Spike | **60,000ms** | **890ms** | **9%** | **0%** | Previously FAILED → now PASSES |
| Soak | 25-28ms | 25ms | 0% | 0% | Similar |
| Breakpoint | **19,300ms** | **389ms** | **9.11%** | **3.43%** | Better but still degraded |
| Recovery | **59,210ms** | **822ms** | **5.13%** | **0%** | Previously FAILED → now PASSES |

**Old infrastructure:** API 2 CPU / 1 GB, PostgreSQL 2 CPU / 1 GB, pool_size=10, max_overflow=20 (30 total), shared_buffers=256MB
**New infrastructure:** API 4 CPU / 2 GB, PostgreSQL 3 CPU / 2 GB, pool_size=60, max_overflow=30 (90 total), shared_buffers=512MB

The three tests that flipped from FAIL to PASS (spike, breakpoint, recovery) all involve high-concurrency scenarios that exhaust connection pools. The 3x increase in pool capacity (30 → 90) was the decisive factor.

---

## Key Conclusions — 1 Uvicorn Worker

### Performance Envelope

| Metric | Value |
|--------|-------|
| Comfortable capacity | 50 VUs / 32 RPS — p(95) 27ms, 0% errors |
| Stress capacity | 300 VUs / 120–174 RPS — p(95) 740–1,634ms; threshold failed in Runs 7 (WSL2) and 9 (genuine CPU saturation) |
| Spike survival | 300 VU burst — p(95) 845–1,933ms, 0% errors (Run 9 barely passes: 1,933ms < 2,000ms) |
| Sustained ceiling | ~43–73 RPS under open-model load — highly variable (moderate collapse, catastrophic collapse, or rare stable degradation) |
| Endurance | 32 min at 30 VUs — zero degradation |

### Architectural Strengths
1. **Excellent endurance** — 32-minute soak with flat latency
2. **Correct concurrency control** — exactly 283 contention bookings, zero deadlocks
3. **Zero errors at moderate load** — load, soak, contention all perfect
4. **Full connection pool** — 90 undivided connections (largest per-worker pool)

### Limitations Under High Load
1. **Single event loop saturates** — with one CPU core doing all processing, 300+ VUs cause queuing
2. **Variable stress ceiling, very variable breakpoint** — Stress has failed the threshold twice across 9 runs: Run 7 (1,616ms — WSL2 fragmentation) and Run 9 (1,634ms — genuine CPU saturation, confirmed by clean 2w/4w). Runs 2–6 and 8 cluster at 740–886ms. Breakpoint is highly variable: three distinct regimes — stable degraded (Runs 2–3, ~1,480ms), moderate collapse (Runs 5–6, 8, and 9, ~69–73 RPS, 3.4–4.75% errors), catastrophic collapse (Runs 4 and 7, 30,000ms+, aborted early).
3. **Slowest recovery** — takes longest to drain request backlog after bursts

### Thesis Takeaway
The single-worker config performs well at moderate concurrency but is the weakest config under high load. Across nine runs, 1w is consistently the worst-performing config at high concurrency — confirming linear scaling where adding workers improves performance. The undivided 90-connection pool is an advantage, but the single event loop is the hard bottleneck above ~100 VUs. Run 7 was anomalous (WSL2 memory fragmentation): stress threshold failed (1,616ms), breakpoint catastrophically collapsed (31,348ms, aborted at 14.7 min). Run 9 is the second stress threshold failure (1,634ms), this time due to genuine CPU saturation — confirmed by clean 2w and 4w results, unlike Run 7 where all configs degraded. Out of 9 runs, 1w stress has failed the threshold twice and breakpoint has catastrophically collapsed twice (Runs 4 and 7). The breakpoint behavior is the most striking demonstration across all nine runs: 4w sustains ~189 RPS with 0% errors every run, while 1w cannot reliably sustain even 73 RPS and collapses catastrophically in 2 of 9 runs (Runs 4 and 7).
