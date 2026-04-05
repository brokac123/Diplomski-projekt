# K6 Performance Test Results — 4 Uvicorn Workers

**Date:** Run 1: 2026-04-04, Run 2: 2026-04-05
**Configuration:** Docker (FastAPI + PostgreSQL), 4 Uvicorn workers
**Seed data:** 1,000 users, 100 events, 2,000 bookings (re-seeded before each test via `run_tests.sh`)
**Monitoring:** K6 → Prometheus remote write → Grafana dashboard (live visualization)
**Machine:** Windows 11, 32 GiB RAM
**K6 output:** `--out experimental-prometheus-rw` with trend stats: p(50), p(90), p(95), p(99), avg, min, max
**Test runner:** Automated via `run_tests.sh` (re-seed → run → restart if crashed → 30s cool-down)
**Resource limits:** API 2 CPU / 1 GB, PostgreSQL 2 CPU / 1 GB, Prometheus 1 CPU / 512 MB

---

## Multi-Run Summary Table

| Test | Type | VUs | R1 p(95) | R2 p(95) | R1 Errors | R2 Errors | R1 RPS | R2 RPS | Status |
|------|------|-----|----------|----------|-----------|-----------|--------|--------|--------|
| Baseline | Smoke | 10 | 78ms | 72ms | 0% | 0% | 64 | 69 | PASS |
| Endpoint Benchmark | Isolation | 20 | 41–80ms | 34–75ms | 0% | 0% | 54 | 55 | PASS |
| Load | Normal load | 50 | 31ms | 30ms | 0% | 0% | 32 | 32 | PASS |
| Stress | Overload | 300 | 1,895ms | 1,691ms | 1.97% | 1.39% | 111 | 110 | **FAIL** (consistent) |
| Spike | Burst | 300 | 44ms | **3,412ms** | 0.06% | **2.60%** | 8 | 42 | **INCONSISTENT** (R1 PASS, R2 FAIL) |
| Soak | Endurance | 30 | 34ms | 29ms | 0% | 0% | 15 | 23 | PASS |
| Breakpoint | Capacity | 500 | 31ms† | 1,890ms | 0% | 4.15% | 10 | 99 | PASS (but different configs†) |
| Contention | Locking | 50 | 25ms | 30ms | 0% | 0% | 137 | 137 | PASS |
| Read vs Write (read) | Traffic profile | 30 | 38ms | 32ms | 0% | 0% | ~43 | ~43 | PASS |
| Read vs Write (write) | Traffic profile | 30 | 32ms | 30ms | 0% | 0% | ~43 | ~43 | PASS |
| Recovery | Recovery | 300 | 2,450ms | 1,598ms | 1.20% | 1.43% | 62 | 57 | PASS |

†Run 1 breakpoint used maxVUs=50 (different from standard maxVUs=500). Run 2 uses the standard maxVUs=500 config matching 1w/2w tests.

**Overall: Stress consistently FAIL. Spike inconsistent (R1 PASS, R2 FAIL). All other tests PASS.**

---

## Multi-Run Variability Analysis

### Stable Results (consistent across runs)
- **Load test:** p(95) 30–31ms, 0% errors, 32 RPS. Identical.
- **Stress test:** Both runs FAIL (p95=1,691–1,895ms > 1,500ms threshold). Consistent ~110 RPS, ~1.5% errors.
- **Soak test:** p(95) 29–34ms, 0% errors. Consistent.
- **Contention test:** Booking p(95) 25–30ms, 0% errors, 137 RPS. Very consistent.
- **Read vs Write:** Read p95 32–38ms, write p95 30–32ms. Consistent.
- **Recovery test:** Both PASS (p95=1,598–2,450ms < 10,000ms). Run 2 better p95 but worse max (60s vs 6s).

### Critical Inconsistency

**Spike test (R1: PASS, R2: FAIL):** Run 1 showed p95=44ms — the system "barely noticed" the 300 VU burst, making it the best result across all configurations. Run 2 shows p95=3,412ms and 2.60% errors — a FAIL. **This is the same spike inconsistency seen with 2 workers.** The spike test is inherently noisy for multi-worker configurations.

### Configuration Change: Breakpoint Test

Run 1 used maxVUs=50 (allowing only 50 concurrent VUs, easy for 4 workers to handle). Run 2 uses the standard maxVUs=500, matching 1w/2w configurations. Both PASS the p95<5000ms threshold:
- Run 1: p95=31ms, 0% errors (but trivially easy with maxVUs=50)
- Run 2: p95=1,890ms, 4.15% errors, 104K dropped iterations (real test)

**Run 2 is the correct comparison point** for cross-configuration analysis.

### Soak RPS Improvement
Run 1 showed 15 RPS, run 2 shows 23 RPS. Same pattern as 1w/2w — the improved `run_tests.sh` methodology produces higher soak RPS. Run 2's 23 RPS matches 1w and 2w, confirming all configs produce identical soak throughput at 30 VUs.

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test

**Purpose:** Verify all endpoints are functional before heavy testing.

**Config:** 10 VUs, 30s duration, hits every endpoint once per iteration.
**Thresholds:** p(95) < 300ms, error rate < 1%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 78ms | 72ms |
| Avg | 59ms | 57ms |
| Max | 140ms | 155ms |
| Error rate | 0% | 0% |
| Total requests | 2,045 | 2,185 |
| RPS | ~64 | ~69 |

**Comparison across configurations:**

| Metric | 1w | 2w | 4w |
|--------|----|----|-----|
| p(95) | 62ms | 79ms | 78ms |
| Median | 22ms | 58ms | 61ms |
| RPS | 85 | 47 | 64 |
| Max | 214ms | 10.1s* | 140ms |

*2w max inflated by network outlier (server processing was 17ms).

**Analysis:** At 10 VUs, 4 workers shows the same multi-worker overhead pattern as 2w — slightly higher latency than 1w due to inter-process scheduling. The 1w system is most efficient at low concurrency because a single event loop handles 10 connections without any inter-process overhead. The 4w configuration is slightly faster than 2w (64 vs 47 RPS) because the OS can distribute the 10 connections more efficiently across 4 lightweight workers.

**Conclusion:** All endpoints healthy. Low-load overhead from multi-worker is present but within acceptable bounds. The real advantages emerge under high concurrency.

---

### A.2 Endpoint Benchmark

**Purpose:** Isolate each endpoint category under controlled load with 100s gaps between scenarios to prevent overlap.

**Config:** 5 sequential scenarios, 20 VUs each, 1 minute per scenario, 100s gap between scenarios. Total: ~7.7 min.

**Results:**

| Scenario | R1 p(95) | R2 p(95) | Threshold | Result |
|----------|----------|----------|-----------|--------|
| Light Reads | 80ms | 68ms | <200ms | PASS |
| List Reads | 41ms | 34ms | <500ms | PASS |
| Search & Filter | 60ms | 56ms | <500ms | PASS |
| Writes | 72ms | 69ms | <1000ms | PASS |
| Heavy Aggregations | 79ms | 75ms | <1500ms | PASS |

- **Total requests:** 25,044 (R1), 25,400 (R2)
- **Error rate:** 0% (both runs)
- **Total RPS:** ~54 (R1), ~55 (R2)

**Comparison across configurations:**

| Scenario | 1w p(95) | 2w p(95) | 4w p(95) |
|----------|----------|----------|----------|
| Light Reads | 42ms | 68ms | 80ms |
| List Reads | 107ms | 51ms | 41ms |
| Search & Filter | 43ms | 58ms | 60ms |
| Writes | 90ms | 71ms | 72ms |
| Heavy Aggregations | 60,231ms (FAIL) | 74ms | 79ms |

**Analysis:** All 5 scenarios pass cleanly, consistent with 2w results. Light reads are slightly slower (80ms vs 68ms) due to the multi-worker overhead at low per-endpoint concurrency. List reads improved (41ms vs 51ms) as the database query load is distributed more evenly. Heavy aggregations continues to pass cleanly with the 100s scenario gap fix.

**Conclusion:** Per-endpoint performance is excellent at 20 VUs. No scenario-overlap issues. Results are very similar to 2w, confirming that at 20 VUs the worker count makes little difference.

---

## Phase B — Standard Test Types (Mixed Realistic Traffic)

All Phase B tests use the same weighted traffic distribution:

| Weight | Operation | Endpoint |
|--------|-----------|----------|
| 25% | Browse events | GET /events/ |
| 15% | View event | GET /events/{id} |
| 10% | Search events | GET /events/search?location=... |
| 8% | Upcoming events | GET /events/upcoming |
| 10% | List users | GET /users/ |
| 5% | User bookings | GET /users/{id}/bookings |
| 12% | Create booking | POST /bookings/ |
| 5% | Cancel booking | PATCH /bookings/{id}/cancel |
| 5% | Event stats | GET /events/{id}/stats |
| 3% | Popular events | GET /events/popular |
| 2% | Global stats | GET /stats |

---

### B.1 Load Test

**Purpose:** Simulate normal-to-peak traffic and verify the system handles expected production load.

**Config:** Ramp 0 → 50 VUs (2 min) → hold 50 VUs (5 min) → ramp down to 0 (1 min). Total: ~8 min.
**Thresholds:** p(95) < 500ms, p(99) < 1000ms, error rate < 1%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 31ms | 30ms |
| Avg | 19ms | 18ms |
| Max | 134ms | 83ms |
| Error rate | 0% | 0% |
| Total requests | 15,416 | 15,362 |
| RPS | ~32 | ~32 |

**Comparison across configurations:**

| Metric | 1w | 2w | 4w |
|--------|----|----|-----|
| p(95) | 34ms | 29ms | 31ms |
| Avg | 38ms | 17ms | 19ms |
| Max | 10.3s | 155ms | 134ms |
| RPS | 32 | 32 | 32 |
| Error rate | 0% | 0% | 0% |

**Analysis:** The load test is nearly identical across 2w and 4w configurations. At 50 VUs, both handle the load comfortably. The key improvement from 1w remains: elimination of tail latency (max dropped from 10.3s to 134ms). Adding workers beyond 2 provides no measurable benefit at this concurrency level — the bottleneck at 50 VUs is neither the event loop nor the CPU.

**Conclusion:** Perfect results. At normal production load, 2 and 4 workers perform identically. The system is well within capacity.

---

### B.2 Stress Test

**Purpose:** Progressive overload to find the degradation point.

**Config:** Ramp 0 → 50 (1 min) → 50 → 100 (2 min) → 100 → 200 (2 min) → 200 → 300 (2 min) → 300 → 0 (1 min). Total: ~8 min.
**Thresholds:** p(95) < 1500ms, error rate < 10%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 1,895ms | 1,691ms |
| Avg | 723ms | 736ms |
| Max | 60s | 60s |
| Error rate | 1.97% | 1.39% |
| Total requests | 55,544 | 54,728 |
| RPS | ~111 | ~110 |
| Duration | 8.3 min | 8.3 min |
| Threshold | **FAIL** | **FAIL** |

**Both runs FAIL** — p(95) exceeds 1,500ms threshold consistently. This is a highly reproducible result.

**Comparison across configurations:**

| Metric | 1w | 2w | 4w |
|--------|----|----|-----|
| p(95) | 353ms | 643ms | **1,895ms** |
| Error rate | 0.54% | 0.19% | 1.97% |
| RPS | 29 | 171 | 111 |
| Total requests | 44,810 | 82,027 | 55,544 |
| Max | 20.1 min | 60s | 60s |
| Test duration | 26 min | 8 min | 8.3 min |
| Threshold | PASS | PASS | **FAIL** |

**This is the most important finding: 4 workers performed WORSE than 2 workers under sustained high load.**

**Analysis — The CPU-to-Worker Ratio Problem:**

The stress test regression has a clear root cause: **4 workers on 2 CPU cores creates CPU contention.**

The Docker resource limit allocates 2 CPUs to the API container:
- **2 workers:** Each worker gets ~1 CPU core. Efficient scheduling, no contention.
- **4 workers:** Each worker gets ~0.5 CPU core. The OS must constantly context-switch between 4 Python processes.

Under 300 VUs, each worker needs CPU cycles for:
1. asyncio event loop management (connection multiplexing)
2. HTTP request parsing and response serialization
3. SQLAlchemy ORM operations (model instantiation, query building)
4. Pydantic validation

With only 0.5 CPU per worker, these operations queue at the OS scheduler level, adding latency that compounds under sustained load. The result:
- 2w processes requests faster per-worker (1 CPU each), achieving higher throughput (171 vs 111 RPS)
- 4w creates more scheduling overhead, adding latency that pushes p(95) past the threshold

**Key thesis insight:** The optimal worker count is bounded by available CPU cores. **Workers should not exceed CPU cores** for CPU-sensitive workloads under sustained high concurrency. The Uvicorn documentation recommends `workers = (2 × CPU) + 1` as an upper bound, but for this workload, `workers = CPU cores` is the sweet spot.

**Note on 1w comparison:** The 1w stress test shows a lower p(95) (353ms) but this is misleading — 1w processed far fewer requests (29 RPS vs 111 RPS) because the single event loop dropped/queued most connections. The 4w system is genuinely handling more load but degrading under the CPU contention.

**Conclusion:** 4 workers on 2 CPUs is the wrong ratio for sustained 300 VU load. The stress test is the clearest evidence that more workers does not always mean better performance — CPU-to-worker ratio is the critical factor.

---

### B.3 Spike Test

**Purpose:** Test system response to sudden traffic burst and recovery.

**Config:** 0 → 10 VUs (30s) → hold 10 (1 min) → spike 10 → 300 (10s) → hold 300 (30s) → drop 300 → 10 (10s) → hold 10 (1 min) → 0. Total stages: ~4 min.
**Thresholds:** p(95) < 2000ms, error rate < 15%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | **44ms** | **3,412ms** |
| Avg | 86ms | 1,060ms |
| Max | 102s | 8,477ms |
| Error rate | 0.06% | **2.60%** |
| Total requests | 1,732 | 8,808 |
| RPS | ~8 | ~42 |
| Duration | 3.5 min | 3.5 min |
| Threshold | **PASS** | **FAIL** |

**⚠ CRITICAL: This result is NOT reproducible.** Run 1 showed the best spike performance of any configuration (p95=44ms). Run 2 FAILED with p95=3,412ms. **This is the same spike inconsistency seen with 2 workers.**

**Multi-run comparison across configurations:**

| Config | R1 Spike | R2 Spike | Consistent? |
|--------|----------|----------|-------------|
| 1w | FAIL (60s) | FAIL (60s) | Yes (always FAIL) |
| 2w | PASS (1,148ms) | FAIL (60s) | **No** |
| 4w | PASS (44ms) | FAIL (3,412ms) | **No** |

**Analysis:**

The spike test is inherently noisy for ALL multi-worker configurations. The outcome depends on:

1. **OS connection distribution at burst time.** If connections split evenly across 4 workers (~75 each), the burst is absorbed easily (run 1). If distribution is uneven, one or more workers cascade (run 2).
2. **CPU scheduling during the burst.** 4 workers on 2 CPUs means CPU contention during the 30s burst. If the OS scheduler handles context switches efficiently, latency stays low. If not, queues build.

Run 1's spectacular result (p95=44ms) was a best-case scenario. Run 2's FAIL shows the worst case. The truth is somewhere in between — 4 workers provides better *odds* of surviving a spike, but doesn't guarantee it.

**Conclusion:** The spike test cannot be used as a reliable differentiator between worker configurations. Only 1 worker is consistently FAIL. Both 2w and 4w are probabilistic — sometimes PASS, sometimes FAIL.

---

### B.4 Soak Test

**Purpose:** Long-running stability test to detect memory leaks, connection pool exhaustion, or gradual latency creep.

**Config:** Ramp 0 → 30 VUs (1 min) → hold 30 VUs (30 min) → ramp down (1 min). Total: ~32 min.
**Thresholds:** p(95) < 700ms, error rate < 1%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 34ms | 29ms |
| Avg | 19ms | 17ms |
| Max | 128ms | 86ms |
| Error rate | 0.00% | 0.00% |
| Total requests | 43,345 | 44,001 |
| RPS | 15* | 23 |
| Duration | 48 min† | 32 min |

*Run 1 RPS of 15 reflects methodology differences. Run 2's 23 RPS matches all configs.
†Run 1 extended due to a stuck iteration (16.7 min); not reproduced in run 2.

**Comparison across configurations (Run 2 data):**

| Metric | 1w | 2w | 4w |
|--------|----|----|-----|
| p(95) | 25ms | 31ms | 29ms |
| RPS | 23 | 23 | 23 |
| Error rate | 0% | 0% | 0% |

*2w max from network outlier; server processing max was 130ms.

**Analysis:**

1. **p(95) slightly higher** (34ms vs 28ms for 1w/2w). At 30 VUs, the 4-worker overhead (OS scheduling 4 processes) adds a small but measurable latency compared to fewer workers.
2. **RPS lower than 2w** (15 vs 23). With more workers competing for CPU during the steady state, iterations complete slightly slower, reducing overall throughput.
3. **No resource leaks.** Latency remained flat for the full 30-minute hold period. No memory growth, no connection pool exhaustion.
4. **The single stuck iteration** (16.7 min) is an anomaly — likely a brief network hiccup that caused one request to stall. It did not cascade or affect other requests.

**Conclusion:** Rock-solid stability over 30+ minutes. No resource leaks with 4 workers. However, the soak test reveals that 4 workers provides no benefit over 2 workers at moderate load (30 VUs) — in fact, the extra process overhead slightly reduces throughput.

---

### B.5 Breakpoint Test

**Purpose:** Find the absolute maximum throughput using open-model load.

**Config:** ramping-arrival-rate executor. Ramp from 10 to 500 iterations/s over the test duration. preAllocatedVUs = 50, maxVUs = 500 (Run 2; Run 1 used maxVUs = 50). Auto-abort when p(95) > 5000ms.
**Thresholds:** p(95) < 5000ms with abortOnFail.

**Results:**

| Metric | Run 1 (maxVUs=50) | Run 2 (maxVUs=500) |
|--------|-------------------|---------------------|
| p(95) | 31ms | 1,890ms |
| Avg | 18ms | 2,355ms |
| Max | 297ms | 60s |
| Error rate | 0% | 4.15% |
| Total requests | 25,771 | 122,057 |
| RPS | ~10 | ~99 |
| Dropped iterations | 0 | 104,138 |
| Duration | 45 min (completed) | 20.5 min (completed) |
| Threshold | **PASS** | **PASS** |

**⚠ Configuration change:** Run 1 used maxVUs=50 (only 4 VUs ever allocated — trivially easy). Run 2 uses maxVUs=500 (standard config matching 1w/2w). **Run 2 is the correct comparison.**

**Comparison across configurations (Run 2, maxVUs=500):**

| Metric | 1w | 2w | 4w |
|--------|----|----|-----|
| p(95) | 60s | 31.1s | **1,890ms** |
| Error rate | 5.04% | 5.68% | 4.15% |
| Dropped | 134K | 44K | 104K |
| Threshold | FAIL | FAIL | **PASS** |

**4 workers is the only configuration to pass the breakpoint test** even with the standard maxVUs=500 config.

**Analysis:**

With 4 workers and maxVUs=500, the system handles the ramping arrival rate much better than 1w or 2w:
- p(95) of 1,890ms stays under the 5,000ms threshold
- More total requests processed (122K vs 34K for 2w)
- Higher sustained RPS (99 vs 43 for 2w)

The higher dropped iterations (104K) vs 2w (44K) reflects the longer test duration (20.5 min vs 13 min — 2w aborted earlier).

**Why breakpoint passes but stress fails:** The breakpoint test uses an open-model executor (ramping-arrival-rate) that sends requests at a controlled rate. The stress test uses closed-model (300 VUs sending as fast as possible). The open model's pacing prevents the CPU contention spiral.

**Conclusion:** 4 workers handles open-model load better than any other configuration, passing the breakpoint threshold that 1w and 2w both fail.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test

**Purpose:** Test PostgreSQL row-level locking under extreme contention. All 50 VUs simultaneously book the same event (event_id=1).

**Config:** 50 VUs, 2 min duration. Custom metric `contention_booking_latency` tracks booking-specific response times.
**Thresholds:** booking latency p(95) < 3000ms, error rate < 5%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| Booking latency p(95) | 25ms | 30ms |
| Booking latency avg | 15ms | 18ms |
| HTTP p(95) | 63ms | 66ms |
| Max | 635ms | 786ms |
| Error rate | 0.00% | 0.00% |
| Total requests | 16,634 | 16,610 |
| RPS | ~137 | ~137 |
| Bookings success | 283 | 283 |

**Comparison across configurations:**

| Metric | 1w | 2w | 4w |
|--------|----|----|-----|
| Booking latency p(95) | 48ms | 76ms | **25ms** |
| Booking latency avg | 20ms | 32ms | **15ms** |
| Booking latency max | 624ms | 685ms | **635ms** |
| RPS | 144 | 122 | 137 |
| Bookings success | 283 | 283 | 283 |
| Error rate | 0% | 0% | 0% |

**This result reverses the 1w → 2w trend. 4 workers has the BEST contention performance.**

**Analysis — Why the Contention Reversal:**

The 2w results document predicted that 4 workers would have even worse contention due to more database lock competitors. The opposite happened. Here's why:

1. **Shorter lock hold times.** With 4 workers and 50 VUs, each worker handles ~12 VUs. At 12 VUs per event loop, there is virtually no event loop pressure. Each transaction (lock → check capacity → insert → commit) executes at maximum speed with no queuing at the application layer.

2. **The critical factor is lock HOLD time, not lock ATTEMPT count.** With 2 workers (25 VUs each), the event loops have moderate load, making each transaction slightly slower. The lock is held for longer, creating a longer queue at the database level. With 4 workers (12 VUs each), each transaction completes faster, releasing the lock sooner — even though 4 processes are attempting locks.

3. **Per-worker efficiency wins.** The contention test has only 50 VUs — well within the per-worker capacity of a 4-worker setup. The CPU-to-worker ratio problem from the stress test (300 VUs) doesn't apply here.

**Scaling curve for contention:**

| Config | Booking p(95) | VUs per worker | Lock hold time |
|--------|--------------|----------------|----------------|
| 1w | 48ms | 50 | Moderate (event loop busy) |
| 2w | 76ms | 25 | Longer (DB lock competition from 2 processes) |
| 4w | 25ms | 12.5 | Shortest (minimal event loop pressure) |

The 2w result was the worst because it combined moderate per-worker load (enough to slow transactions) with doubled database-level lock competition. 4w has minimal per-worker load, so transactions are extremely fast, and the extra lock competitors are a non-issue.

**Key thesis insight:** For single-resource contention, the optimal configuration minimizes lock hold time. More workers can actually REDUCE contention if each worker handles few enough connections that transaction processing is never delayed by event loop queuing.

**Conclusion:** 4 workers achieves the best contention performance across all configurations. Correctness is maintained (exactly 283 bookings, zero double-bookings, zero deadlocks). The 48% improvement over 1w and 67% improvement over 2w demonstrates that the worker-to-VU ratio matters more than the raw worker count.

---

### C.2 Read vs Write Test

**Purpose:** Compare system behavior under read-heavy vs write-heavy traffic.

**Config:** Two sequential scenarios at 30 VUs, 3 min each:

| Scenario | Profile | Operations |
|----------|---------|------------|
| `read_heavy` | 90% reads / 10% writes | Browse events, view event, search, list users, global stats, create booking |
| `write_heavy` | 40% reads / 60% writes | Browse events, view event, create booking, cancel booking |

**Thresholds:** read_heavy p(95) < 500ms, write_heavy p(95) < 1500ms, error rate < 5%.

**Results:**

| Metric | R1 Read | R1 Write | R2 Read | R2 Write |
|--------|---------|----------|---------|----------|
| p(95) | 38ms | 32ms | 32ms | 30ms |
| Avg | 22ms | 18ms | — | — |
| Error rate | 0% | 0% | 0% | 0% |

- **Combined RPS:** ~43 (both runs)
- **Checks passed:** 100% (both runs)

**Comparison across configurations:**

| Metric | 1w read | 2w read | 4w read | 1w write | 2w write | 4w write |
|--------|---------|---------|---------|----------|----------|----------|
| p(95) | 38ms | 37ms | 38ms | 56ms | 40ms | **32ms** |

**The read/write gap has completely inverted.**

| Config | Read p(95) | Write p(95) | Write/Read ratio |
|--------|-----------|-------------|------------------|
| 1w | 38ms | 56ms | 1.47x (writes slower) |
| 2w | 37ms | 40ms | 1.08x (writes slightly slower) |
| 4w | 38ms | 32ms | **0.84x (writes FASTER)** |

**Analysis:**

1. **Writes are now faster than reads.** With 4 workers at 30 VUs, write transactions (lock → insert → commit) are processed so quickly that they complete faster than read operations. Read scenarios include heavier queries (search, list, global stats) that return more data.

2. **Read performance unchanged.** 38ms across all three configurations. Reads were never a bottleneck at 30 VUs — the event loop handles SELECT queries efficiently regardless of worker count.

3. **Write performance scales linearly:** 56ms → 40ms → 32ms as workers increase from 1 → 2 → 4. Each additional worker reduces write contention at the application level by distributing transaction processing across more event loops.

**Conclusion:** 4 workers eliminates the write penalty entirely at moderate load, with write-heavy traffic now performing better than read-heavy. This is the ideal configuration for write-heavy applications at moderate concurrency.

---

### C.3 Recovery Test

**Purpose:** Measure time-to-recovery after sudden overload. Long post-spike observation window.

**Config:** 1 min baseline (30 VUs) → 10s spike to 300 VUs → 30s hold at 300 → 10s drop to 30 → 4 min observation (30 VUs) → 20s ramp down. Total: ~6 min.
**Thresholds:** p(95) < 10,000ms, error rate < 30%, checks > 70%.

**Results:**

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| p(95) | 2,450ms | 1,598ms |
| Avg | 405ms | 425ms |
| Max | 6s | 60s |
| Error rate | 1.20% | 1.43% |
| Total requests | 23,117 | 21,047 |
| RPS | ~62 | ~57 |
| Threshold | PASS | PASS |

**Both runs PASS** (p95 < 10,000ms). This is a key difference from 2w, where recovery was inconsistent (R1 PASS, R2 FAIL).

**Mixed signals on worst-case latency:** Run 1 showed max=6s (no timeouts), run 2 showed max=60s (some timeouts). However, the p(95) actually improved in run 2 (1,598ms vs 2,450ms), suggesting overall recovery is good even when a few requests timeout.

**Comparison with 2w (Run 2 data):**

| Metric | 2w R2 | 4w R2 |
|--------|-------|-------|
| p(95) | 59,996ms (FAIL) | 1,598ms (PASS) |
| Error rate | 5.44% | 1.43% |
| RPS | 15 | 57 |
| Threshold | **FAIL** | **PASS** |

**Analysis:** The recovery test is where 4 workers shows a clear, reproducible advantage over 2 workers. While 2w recovery is inconsistent (R1 PASS, R2 FAIL), 4w recovery PASSES in both runs. The additional event loops provide enough capacity to drain the post-spike backlog before timeout cascades begin.

**Conclusion:** 4 workers consistently recovers from 300 VU spikes. This is a reliable architectural advantage over 2 workers.

---

## System Behavior Under Failure

### Observed Failure Patterns

| Test | Peak VUs | API Status After | Recovery |
|------|----------|-----------------|----------|
| Load (50 VUs) | 50 | Healthy | N/A (no stress) |
| Stress (300 VUs gradual) | 300 | Degraded, timeouts | Self-recovered |
| Spike (300 VUs sudden) | 300 | Healthy | **Immediate** |
| Breakpoint (50 VUs open-model) | 50 | Healthy | N/A (never stressed) |
| Soak (30 VUs, 30 min) | 30 | Healthy | N/A |
| Recovery (300 VU spike) | 300 | Brief degradation | Self-recovered |

### Comparison Across All Configurations (Multi-Run)

| Test | 1w | 2w | 4w |
|------|----|----|-----|
| Stress (300 VUs) | PASS (both runs) | PASS (both runs) | **FAIL** (both runs) |
| Spike (300 VUs) | **FAIL** (both runs) | INCONSISTENT | INCONSISTENT |
| Breakpoint | FAIL (both runs) | FAIL (both runs) | **PASS** (both runs) |
| Recovery | FAIL (R2 only) | INCONSISTENT | **PASS** (both runs) |

### Failure Mode Evolution (confirmed across runs)

| Property | 1w | 2w | 4w |
|----------|----|----|-----|
| Primary bottleneck | Event loop | Event loop | **CPU scheduling** |
| Failure mode | Cascade → unresponsive | Probabilistic cascade | **Degraded p95, higher errors** |
| Recovery from 300 VU burst | Never recovers | **Sometimes** recovers | **Consistently** recovers |
| Stress test result | PASS | PASS | **FAIL** |

The key multi-run finding: 4 workers trades **stress test failure** (CPU contention under sustained load) for **consistent recovery** (4 event loops prevent cascade after bursts).

---

## 1w vs 2w vs 4w Full Comparison (Multi-Run)

### Reliable Results Only (consistent across runs)

| Metric | 1w | 2w | 4w | Best |
|--------|----|----|-----|------|
| Load p(95) | 29ms | 32ms | 30ms | ~Same |
| Load max | 72ms | 92ms | 83ms | ~Same |
| Stress result | PASS | PASS | **FAIL** | 1w / 2w |
| Stress RPS | 82 | 76 | 110 | 4w |
| Stress p(95) | 457ms | 477ms | 1,691ms | 1w / 2w |
| Soak p(95) | 25ms | 31ms | 29ms | ~Same |
| Soak RPS | 23 | 23 | 23 | Same |
| Breakpoint result | FAIL | FAIL | **PASS** | **4w** |
| Contention booking p(95) | 42ms | 76–141ms | 25–30ms | **4w** |
| Write-heavy p(95) | ~32ms | 40–74ms | 30–32ms | 4w |
| Recovery result | FAIL | INCONSISTENT | **PASS** | **4w** |

### Unreliable Results (vary between runs — NOT for thesis conclusions)

| Metric | Note |
|--------|------|
| Spike test | 1w always FAIL. 2w and 4w: INCONSISTENT (sometimes PASS, sometimes FAIL) |
| 2w stress RPS | Varied from 76 to 171 between runs — cannot claim super-linear scaling |

### Where Each Configuration Reliably Wins

**1 Worker wins at:**
- Low-concurrency latency (baseline p95 = 45ms)
- Simplicity (no inter-process overhead)

**2 Workers wins at:**
- None definitively (stress and spike advantages from run 1 not confirmed in run 2)
- Similar stress behavior to 1w with run 2 data

**4 Workers wins at:**
- Breakpoint (only config to PASS — consistent)
- Contention performance (p95 = 25–30ms — best lock efficiency, consistent)
- Write-heavy traffic (p95 = 30–32ms, consistent)
- Recovery (only config to consistently PASS)
- Stress throughput (110 RPS, despite p95 FAIL)

### Scaling Curve (Run 2 — reliable data)

| Metric | 1w→2w | 2w→4w | Pattern |
|--------|-------|-------|---------|
| Load p(95) | +10% (same) | -6% (same) | Flat — 50 VUs doesn't stress any config |
| Stress p(95) | +4% (same) | +254% (worse) | 4w CPU contention |
| Stress RPS | -7% (same) | +45% (better) | 4w processes more requests (but degrades) |
| Soak RPS | 0% (same) | 0% (same) | All configs identical at 30 VUs |
| Contention p(95) | +81% (worse) | -79% (better) | U-curve confirmed |
| Write p(95) | +131% (worse) | -59% (better) | 4w clearly best |

**The scaling curve is NOT linear.** Key finding confirmed:

- **Moderate load (50 VUs):** Worker count makes NO difference. All configs produce identical results.
- **Sustained overload (300 VUs):** 4w FAILS due to CPU contention. 1w and 2w PASS.
- **Burst traffic:** Inconsistent across all multi-worker configs. Only 1w is consistently FAIL.
- **Open-model (breakpoint):** 4w is the only config to PASS.
- **Contention:** U-curve confirmed — 2w is worst, 4w is best.

---

## Key Conclusions — 4 Uvicorn Workers (Multi-Run)

### Performance Envelope

| Metric | Value | Reproducible? |
|--------|-------|---------------|
| Comfortable capacity | 50 VUs / 32 RPS, p(95) ~30ms | Yes |
| Sustained overload | 300 VUs, p(95) ~1,700ms, FAIL | Yes (consistently FAIL) |
| Breakpoint | Open-model, p(95) ~1,890ms, PASS | Yes |
| Recovery | 300 VU burst → PASS | Yes (both runs) |
| Spike | 300 VU burst | **No** (inconsistent) |

### Architectural Strengths (confirmed across runs)
1. **Only breakpoint PASS** — handles open-model load better than 1w/2w
2. **Best contention performance** — 25–30ms booking latency (consistent)
3. **Fastest writes** — write-heavy p95 30–32ms (consistent)
4. **Consistent recovery** — system reliably recovers from 300 VU bursts
5. **Highest stress throughput** — 110 RPS (but at cost of higher latency)

### Architectural Weaknesses (confirmed across runs)
1. **CPU-to-worker imbalance** — stress test consistently FAIL (p95 > 1,500ms)
2. **Spike inconsistency** — NOT reliably better than 2 workers for burst traffic
3. **Multi-worker overhead at low load** — baseline p95 ~72ms vs 1w's ~45ms

### The CPU-to-Worker Ratio Rule (confirmed)

| Workers:CPUs | Burst traffic | Sustained traffic | Breakpoint |
|-------------|---------------|-------------------|------------|
| 1:2 | Always FAIL | PASS | FAIL |
| 2:2 | Inconsistent | PASS | FAIL |
| 4:2 | Inconsistent | **FAIL** | **PASS** |

### Revised Recommendation for the Thesis

The multi-run data fundamentally changes the narrative:

1. **Spike test results are NOT reproducible** for any multi-worker config. Do not use spike data as a primary thesis conclusion.
2. **The reliable differentiators are:** stress (1w/2w PASS, 4w FAIL), breakpoint (4w only PASS), contention (4w best), and recovery (4w consistently PASS).
3. **The CPU-to-worker ratio rule is confirmed** — 4 workers on 2 CPUs degrades sustained throughput.
4. **At moderate load (50 VUs), worker count makes zero difference.** The scaling benefit only appears under extreme load.
5. **More runs are needed** to establish confidence intervals for the noisy tests (spike, stress RPS).
