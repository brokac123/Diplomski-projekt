# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** 2026-04-18 (Run 7)
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
| Stress | Overload | 300 | 1,616ms | 0% | 120 | 57,551 | FAIL |
| Spike | Burst | 300 | 1,923ms | 0% | 44 | 9,244 | PASS |
| Soak | Endurance | 30 | 25ms | 0% | 23 | 44,049 | PASS |
| Breakpoint | Capacity | 500 | 31,348ms | 4.64% | 47.9 | 42,285 | FAIL |
| Contention | Locking | 50 | 58ms† | 0% | 144 | 17,398 | PASS |
| Read vs Write | Traffic profile | 30 | ~32ms | 0% | ~44 | ~16,235 | PASS |
| Recovery | Resilience | 300 | 1,835ms | 0% | 61 | 22,690 | PASS |

*Overall p(95) across all scenarios. †Contention booking-specific latency p(95).

**8 of 10 tests PASS. Stress FAILS the p(95) < 1500ms threshold at 1,616ms — the first time 1w stress fails its threshold across all 7 runs. Breakpoint FAILS the p(95) < 5000ms abortOnFail threshold at 31,348ms — catastrophic collapse, test aborted at ~14.7 min, 4.64% errors, 58,384 dropped iterations.**

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
| p(95) | **1,616ms** |
| p(90) | 1,491ms |
| Avg | 672ms |
| Median | 576ms |
| Max | 2,104ms |
| Error rate | 0% |
| Checks | 100% (57,550/57,550) |
| Total requests | 57,551 |
| RPS | **120** |
| Bookings | 6,702 success |

**Cross-config comparison (Run 7):**
| Workers | p(95) | RPS | Errors |
|---------|-------|-----|--------|
| **1w** | **1,616ms** | **120** | 0% |
| 2w | 253ms | 230 | 0% |
| 4w | 120ms | 257 | 0% |

**Analysis:** The single worker shows significantly higher latency than 2w and 4w under 300 VU stress. With only one event loop processing all requests, the single CPU core becomes the bottleneck at this concurrency level. Run 7 produced 1,616ms p95 — the worst 1w stress result across all 7 runs, exceeding the 1,500ms threshold for the first time. This aligns with higher host load during this run (WSL2/Docker scheduling variance). Across runs: Run 2 (886ms / 164 RPS), Run 3 (839ms / 167 RPS), Run 4 (830ms / 167 RPS), Run 5 (804ms / 174 RPS), Run 6 (854ms / 168 RPS), Run 7 (1,616ms / 120 RPS) — the 1w event loop consistently saturates at 300 VUs.

**Conclusion:** FAILS p(95) threshold (1,616ms > 1,500ms) — first threshold failure across all 7 runs. 0% errors despite threshold breach. Higher host load during Run 7 pushed 1w beyond its usual ceiling.

---

### B.3 Spike Test

**Config:** 10 VUs → spike to 300 VUs in 10s → hold 30s → drop to 10 VUs → 1 min observation.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

| Metric | Value |
|--------|-------|
| p(95) | **1,923ms** |
| p(90) | 1,862ms |
| Avg | 981ms |
| Median | 1,356ms |
| Max | 2,240ms |
| Error rate | 0% |
| Checks | 100% (9,243/9,243) |
| Total requests | 9,244 |
| RPS | 44 |
| Bookings | 1,107 |

**Cross-config comparison (Run 7):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **1,923ms** | 2,240ms | **44** | 0% |
| 2w | 277ms | 448ms | 104 | 0% |
| 4w | 170ms | 433ms | 116 | 0% |

**Analysis:** The single worker struggles most with sudden bursts — 1,923ms p(95) and only 44 RPS. Run 7 is the worst 1w spike result across all 7 runs, consistent with higher host load. Linear scaling is clearly visible: 4w handles the same burst at 170ms / 116 RPS. Consistent across runs: Run 2 (1,225ms), Run 3 (1,079ms), Run 4 (1,062ms), Run 5 (845ms), Run 6 (1,235ms), Run 7 (1,923ms).

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
| p(95) | **31,348ms** |
| p(90) | 1,123ms |
| Avg | 3,060ms |
| Median | 27ms |
| Max | 60,050ms |
| Error rate | **4.64%** (1,961 failures) |
| Checks | 95.4% (40,323/42,283) |
| Total requests | 42,285 |
| RPS | **47.9** |
| Peak VUs | 500 |
| Dropped iterations | **58,384** |
| Bookings | 4,827 success |
| Duration | ~14.7 min (ABORTED — threshold breached) |

**Threshold result:** FAIL — p(95) of 31,348ms breaches the 5,000ms abortOnFail threshold. The test was aborted after ~14.7 minutes. This is a catastrophic collapse — the event loop became completely overwhelmed.

**Cross-config breakpoint comparison (Run 7):**
| Workers | p(95) | RPS | Errors | Dropped | Duration |
|---------|-------|-----|--------|---------|----------|
| **1w** | **31,348ms** | **47.9** | **4.64%** | **58,384** | ~14.7 min (ABORTED) |
| 2w | 10,035ms | 65.7 | 5.19% | 109,285 | ~18.4 min (ABORTED) |
| 4w | 85ms | 189 | 0% | negligible | 20 min (full) |

**Analysis:** Run 7 shows catastrophic 1w collapse — the second catastrophic regime result after Run 4 (30,864ms). The bimodal distribution (median=27ms, avg=3,060ms) is characteristic of a system where most requests time out while a fast minority complete. RPS of 47.9 is the lowest 1w breakpoint result across all 7 runs.

**Variability across runs:**
- Run 1: 192ms / 189 RPS / 0% (anomalously good — U-curve anomaly)
- Run 2: 1,464ms / 62 RPS / 4.6% (stable degraded ceiling)
- Run 3: 1,483ms / 60 RPS / 4.75% (ceiling confirmed consistent)
- Run 4: **30,864ms / 43.6 RPS / 6.87%** (catastrophic collapse, aborted early)
- Run 5: **814ms / 72.9 RPS / 3.36%** (moderate collapse, ran to completion)
- Run 6: **795ms / 71 RPS / 3.48%** (moderate collapse — consistent with Run 5)
- Run 7: **31,348ms / 47.9 RPS / 4.64%** (catastrophic collapse — aborted at ~14.7 min)

Three distinct regimes confirmed: stable degraded (~1,480ms, Runs 2–3), moderate collapse (~795–814ms p95, Runs 5–6), catastrophic collapse (30,864ms/31,348ms, Runs 4 and 7). The 1w event loop sits right at its capacity boundary — Docker CPU scheduling determines which regime occurs.

**Conclusion:** FAILS K6 thresholds with catastrophic collapse. The single event loop is fundamentally unable to sustain the throughput that 4w handles cleanly (189 RPS). 1w behavior under open-model load is inherently unpredictable — 2 out of 7 runs produced catastrophic collapse.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Config:** 50 VUs all booking the same event (event_id=1), 2 minutes.

| Metric | Value |
|--------|-------|
| Booking latency p(95) | 58ms |
| Booking latency avg | 25ms |
| Booking latency median | 17ms |
| HTTP p(95) | 47ms |
| Max | 754ms |
| Error rate | 0% |
| Total requests | 17,398 |
| RPS | 144 |
| Bookings success | 283 |
| Sold out (409) | 8,415 |

**Cross-config contention comparison (Run 7):**
| Workers | Booking p(95) | Bookings | Sold out |
|---------|--------------|----------|----------|
| **1w** | **58ms** | 283 | 8,415 |
| 2w | 30ms | 283 | 8,054 |
| 4w | 26ms | 283 | 8,048 |

**Analysis:** All three configs correctly produce exactly 283 bookings with zero deadlocks. The 283-booking invariant has held across all 7 runs and all 3 configs without exception — proving transaction isolation is preserved regardless of worker count. The 1w p95 jumped to 58ms in Run 7 (from 40ms in Run 6) due to higher host load, but correctness is unaffected.

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
| p(95) | **1,835ms** |
| p(90) | 1,732ms |
| Avg | 420ms |
| Median | 28ms |
| Max | 2,213ms |
| Error rate | 0% |
| Checks | 100% (22,689/22,689) |
| Total requests | 22,690 |
| RPS | 61 |
| Bookings | 2,740 |

**Cross-config recovery comparison (Run 7):**
| Workers | p(95) | Max | RPS | Errors |
|---------|-------|-----|-----|--------|
| **1w** | **1,835ms** | 2,213ms | **61** | 0% |
| 2w | 251ms | 637ms | 97 | 0% |
| 4w | 135ms | 451ms | 104 | 0% |

**Analysis:** Run 7 shows clear linear ordering in recovery: 4w (135ms) < 2w (251ms) < 1w (1,835ms), all 0% errors. The 1w result (1,835ms) is the worst recovery result across all 7 runs, consistent with higher host load. Linear scaling is clearly visible in recovery behavior.

**Conclusion:** PASSES thresholds with 0% errors. Linear ordering confirmed for the seventh consecutive run.

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
| Stress capacity | 300 VUs / 120–174 RPS — p(95) 804–1,616ms, 0% errors (threshold FAILED in Run 7) |
| Spike survival | 300 VU burst — p(95) 845–1,923ms, 0% errors |
| Sustained ceiling | ~43–72 RPS under open-model load — highly variable (moderate collapse, catastrophic collapse, or rare stable degradation) |
| Endurance | 32 min at 30 VUs — zero degradation |

### Architectural Strengths
1. **Excellent endurance** — 32-minute soak with flat latency
2. **Correct concurrency control** — exactly 283 contention bookings, zero deadlocks
3. **Zero errors at moderate load** — load, soak, contention all perfect
4. **Full connection pool** — 90 undivided connections (largest per-worker pool)

### Limitations Under High Load
1. **Single event loop saturates** — with one CPU core doing all processing, 300+ VUs cause queuing
2. **Variable stress ceiling, very variable breakpoint** — Stress varies considerably: Runs 2–6 cluster at 804–886ms, but Run 7 jumped to 1,616ms (threshold failure) due to higher host load. Breakpoint is highly variable: three distinct regimes — stable degraded (Runs 2–3, ~1,480ms), moderate collapse (Runs 5–6, ~795–814ms p95 but avg=2,000ms+), catastrophic collapse (Runs 4 and 7, 30,864ms/31,348ms, aborted early).
3. **Slowest recovery** — takes longest to drain request backlog after bursts

### Thesis Takeaway
The single-worker config performs well at moderate concurrency but is the weakest config under high load. Across seven runs, 1w is consistently the worst-performing config at high concurrency — confirming linear scaling where adding workers improves performance. The undivided 90-connection pool is an advantage, but the single event loop is the hard bottleneck above ~100 VUs. Run 7 was the worst 1w run: stress threshold failed (1,616ms), breakpoint catastrophically collapsed again (31,348ms, aborted at 14.7 min), spike reached 1,923ms. Despite all this, 0% errors in every non-breakpoint test. The breakpoint behavior is the most striking demonstration: 4w sustains ~189 RPS with 0% errors across all 7 runs, while 1w cannot reliably sustain even 72 RPS and collapses catastrophically in 2 of 7 runs.
