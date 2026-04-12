# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** 2026-04-12 (Run 5)
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
| Stress | Overload | 300 | 804ms | 0% | 174 | 83,631 | PASS |
| Spike | Burst | 300 | 845ms | 0% | 67 | 14,081 | PASS |
| Soak | Endurance | 30 | 25ms | 0% | 23 | 44,153 | PASS |
| Breakpoint | Capacity | 500 | 814ms | 3.36% | 72.9 | 89,619 | PASS* |
| Contention | Locking | 50 | 40ms† | 0% | 146 | 17,624 | PASS |
| Read vs Write | Traffic profile | 30 | ~32ms | 0% | ~44 | ~16,206 | PASS |
| Recovery | Resilience | 300 | 851ms | 0% | 74 | 27,557 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**9 of 10 tests PASS with 0% errors. Breakpoint passes the K6 p(95) < 5000ms threshold (814ms) but shows 3.36% errors and 136,452 dropped iterations — moderate collapse. The event loop is at its capacity boundary under open-model load.**

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
| p(95) | **804ms** |
| p(90) | 675ms |
| Avg | 306ms |
| Median | 254ms |
| Max | 1,178ms |
| Error rate | 0% |
| Checks | 100% (83,630/83,630) |
| Total requests | 83,631 |
| RPS | **174** |
| Bookings | 9,663 success |

**Cross-config comparison (Run 5):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **804ms** | **174** | 0% |
| 2w | 239ms | 233 | 0% |
| 4w | 218ms | 243 | 0% |

**Analysis:** The single worker shows significantly higher latency than 2w and 4w under 300 VU stress. With only one event loop processing all requests, the single CPU core becomes the bottleneck at this concurrency level. The connection pool (90 total) has plenty of capacity — CPU, not connections, is the limiting factor. This result is highly consistent across runs: Run 2 (886ms / 164 RPS), Run 3 (839ms / 167 RPS), Run 4 (830ms / 167 RPS), Run 5 (804ms / 174 RPS) — the 1w ceiling is stable across all runs.

**Conclusion:** PASSES with 0% errors but the highest latency among all configs. The single event loop is saturated at 300 VUs.

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 VUs in 10s → hold 30s → drop to 10 VUs → 1 min observation.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **845ms** |
| p(90) | 785ms |
| Avg | 466ms |
| Median | 589ms |
| Max | 1,176ms |
| Error rate | 0% |
| Checks | 100% (14,080/14,080) |
| Total requests | 14,081 |
| RPS | 67 |
| Bookings | 1,686 |

**Cross-config comparison (Run 5):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **845ms** | 1,176ms | **67** | 0% |
| 2w | 333ms | 579ms | 102 | 0% |
| 4w | 160ms | 458ms | 118 | 0% |

**Analysis:** The single worker struggles most with sudden bursts — 845ms p(95) and only 67 RPS. With one event loop, the 300 VU spike saturates the CPU and all requests queue. Linear scaling is clearly visible: 4w handles the same burst at 160ms / 118 RPS. Consistent across runs: Run 2 (1,225ms), Run 3 (1,079ms), Run 4 (1,062ms), Run 5 (845ms).

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
| p(95) | **814ms** |
| p(90) | 237ms |
| Avg | 2,096ms |
| Median | 16ms |
| Max | 60,009ms |
| Error rate | **3.36%** (3,014 failures) |
| Checks | 96.6% (86,604/89,618) |
| Total requests | 89,619 |
| RPS | **72.9** |
| Peak VUs | 500 |
| Dropped iterations | **136,452** |
| Bookings | 10,179 success |
| Duration | ~20.5 min (ran to completion) |

**Threshold result:** PASS* — p(95) of 814ms is below the 5,000ms abortOnFail threshold, so the test ran to completion. However, 3.36% error rate and 136,452 dropped iterations indicate the event loop is under severe stress.

**Cross-config breakpoint comparison (Run 5):**
| Workers | p(95) | RPS | Errors | Dropped | Duration |
|---------|-------|-----|--------|---------|----------|
| **1w** | **814ms** | **72.9** | **3.36%** | **136,452** | ~20.5 min |
| 2w | 1,108ms | 134.9 | 0.62% | 60,415 | ~20.5 min |
| 4w | 50ms | 188.7 | 0% | 23 | 20 min |

**Analysis:** Run 5 shows moderate 1w collapse — the event loop is severely stressed (avg=2,096ms, 136K dropped) but the p95 stays under 5,000ms so the test doesn't abort. The bimodal distribution (median=16ms, avg=2,096ms) shows most requests either complete quickly or time out. RPS of 72.9 (vs 189 for 4w) confirms the 1w ceiling. 4w remains rock-solid at ~189 RPS / 0% errors.

**Variability across runs:**
- Run 1: 192ms / 189 RPS / 0% (anomalously good — U-curve anomaly)
- Run 2: 1,464ms / 62 RPS / 4.6% (stable degraded ceiling)
- Run 3: 1,483ms / 60 RPS / 4.75% (ceiling confirmed consistent)
- Run 4: **30,864ms / 43.6 RPS / 6.87%** (catastrophic collapse, aborted early)
- Run 5: **814ms / 72.9 RPS / 3.36%** (moderate collapse, ran to completion)

Three distinct regimes observed: stable degraded (~1,480ms, Runs 2–3), moderate collapse (814ms p95 but avg=2,096ms, Run 5), catastrophic collapse (30,864ms, Run 4). The 1w event loop sits right at its capacity boundary — Docker CPU scheduling determines which regime occurs.

**Conclusion:** PASSES K6 thresholds in Run 5 but shows significant degradation. The single event loop is fundamentally unable to sustain the throughput that 4w handles cleanly (189 RPS). 1w behavior under open-model load is inherently unpredictable.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking the same event (event_id=1), 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 40ms |
| Booking latency avg | 19ms |
| Booking latency median | 13ms |
| HTTP p(95) | 36ms |
| Max | 706ms |
| Error rate | 0% |
| Total requests | 17,624 |
| RPS | 146 |
| Bookings success | 283 |
| Sold out (409) | 8,528 |

**Cross-config contention comparison (Run 5):**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| **1w** | **40ms** | 283 | 8,528 |
| 2w | 29ms | 283 | 8,036 |
| 4w | 25ms | 283 | 8,174 |

**Analysis:** All three configs correctly produce exactly 283 bookings with zero deadlocks. The 283-booking invariant has held across all 5 runs and all 3 configs without exception — proving transaction isolation is preserved regardless of worker count.

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
| p(95) | **851ms** |
| p(90) | 765ms |
| Avg | 255ms |
| Median | 31ms |
| Max | 1,077ms |
| Error rate | 0% |
| Checks | 100% (27,556/27,556) |
| Total requests | 27,557 |
| RPS | 74 |
| Bookings | 3,333 |

**Cross-config recovery comparison (Run 5):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **851ms** | 1,077ms | **74** | 0% |
| 2w | 448ms | 680ms | 86 | 0% |
| 4w | 142ms | 692ms | 103 | 0% |

**Analysis:** Run 5 produces the clearest recovery ordering across all runs: 4w (142ms) < 2w (448ms) < 1w (851ms), all 0% errors. The 1w max of 1,077ms (vs 60,003ms in Run 4) confirms Run 4 was anomalous. RPS of 74 is the best 1w recovery result across all runs. Linear scaling is clearly visible in recovery behavior.

**Conclusion:** PASSES thresholds with 0% errors. The best 1w recovery result across all runs.

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
| Stress capacity | 300 VUs / 174 RPS — p(95) 804ms, 0% errors |
| Spike survival | 300 VU burst — p(95) 845ms, 0% errors |
| Sustained ceiling | ~43–189 RPS under open-model load — highly variable (ranges from moderate degradation to catastrophic collapse) |
| Endurance | 32 min at 30 VUs — zero degradation |

### Architectural Strengths
1. **Excellent endurance** — 32-minute soak with flat latency
2. **Correct concurrency control** — exactly 283 contention bookings, zero deadlocks
3. **Zero errors at moderate load** — load, soak, contention all perfect
4. **Full connection pool** — 90 undivided connections (largest per-worker pool)

### Limitations Under High Load
1. **Single event loop saturates** — with one CPU core doing all processing, 300+ VUs cause queuing
2. **Consistent stress ceiling, variable breakpoint** — Stress is consistent across Runs 2–5 (886ms→839ms→830ms→804ms). Breakpoint is highly variable: three distinct regimes observed — stable degraded (Runs 2–3, ~1,480ms), moderate collapse (Run 5, 814ms p95 but avg=2,096ms, 136K dropped), catastrophic collapse (Run 4, 30,864ms, aborted early).
3. **Slowest recovery** — takes longest to drain request backlog after bursts

### Thesis Takeaway
The single-worker config performs well at moderate concurrency but is the weakest config under high load. Across five runs, 1w is consistently the worst-performing config at high concurrency — confirming linear scaling where adding workers improves performance. The undivided 90-connection pool is an advantage, but the single event loop is the hard bottleneck above ~100 VUs. The breakpoint behavior is the most striking demonstration: 4w sustains ~189 RPS with 0% errors across all 5 runs, while 1w cannot reliably sustain even 73 RPS and can collapse catastrophically (Run 4: 30,864ms p95, 6.87% errors, 80,420 dropped iterations).
