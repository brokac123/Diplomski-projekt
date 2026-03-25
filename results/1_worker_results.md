# K6 Performance Test Results — 1 Uvicorn Worker

**Date:** 2026-03-25
**Configuration:** Docker (FastAPI + PostgreSQL), 1 Uvicorn worker
**Seed data:** 1,000 users, 100 events, 2,000 bookings

---

## Summary Table

| Test | VUs | Duration | p(95) | Median | Avg | Error Rate | RPS | Status |
|------|-----|----------|-------|--------|-----|------------|-----|--------|
| Baseline | 10 | 30s | 62ms | — | — | 0% | — | PASS |
| Endpoint Benchmark | 20 | 5x1min | see below | — | — | 0% | — | PASS |
| Load | 50 | 8min | 48ms | — | 22.5ms | 0% | 40 | PASS |
| Stress | 300 | 8min | 432ms | 194ms | 963ms | 1.22% | 90 | PASS |
| Spike | 300 | 3.5min | 60s | 27ms | 5.45s | 7.99% | 13 | FAIL |
| Soak | 30 | 32min | 44ms | 17.5ms | 23.4ms | 0% | 12 | PASS |
| Breakpoint | 500 RPS target | 2min (aborted) | 30.4s | 15ms | 1.99s | 3.22% | 11 | ABORT |
| Contention | 50 | 2min | 122ms | 37.5ms | 49ms | 0% | 166 | PASS |
| Read vs Write (read) | 30 | 3min | 77ms | 26ms | 33ms | 0% | — | PASS |
| Read vs Write (write) | 30 | 3min | 130ms | 31ms | 49ms | 0% | — | PASS |

---

## Phase A — Baseline & Endpoint Benchmark

### A.1 Baseline (Smoke) Test
- **Purpose:** Verify all endpoints are functional before heavy testing.
- **Config:** 10 VUs, 30s, thresholds: p(95)<300ms, error rate <1%
- **Result:** PASSED
  - p(95) = 62ms
  - Error rate = 0%
  - Checks = 100%
- **Conclusion:** All endpoints healthy and responsive under minimal load.

### A.2 Endpoint Benchmark
- **Purpose:** Isolate each endpoint category to measure individual performance.
- **Config:** 5 sequential scenarios, 20 VUs each, 1 min per scenario.

| Endpoint Category | Endpoints | p(95) | Threshold |
|-------------------|-----------|-------|-----------|
| Light Reads | GET /health, /users/{id}, /events/{id}, /bookings/{id} | 80ms | <200ms |
| Search & Filter | GET /events/search, /events/upcoming, /users/{id}/bookings, /events/{id}/bookings | 93ms | <500ms |
| Heavy Aggregations | GET /events/{id}/stats, /events/popular, /stats | 100ms | <1500ms |
| Writes | POST /bookings/, PATCH /bookings/{id}/cancel | 144ms | <1000ms |
| List Reads | GET /users/, /events/, /bookings/ (limit=100) | 196ms | <500ms |

- **Conclusion:** PK lookups are fastest (80ms). List reads are slowest (196ms) due to serializing large result sets. Writes (144ms) include row locking overhead. Heavy aggregations (100ms) are well-optimized thanks to DB indexes.

---

## Phase B — Standard Test Types (Mixed Realistic Traffic)

All Phase B tests use the same weighted traffic distribution:
- 25% browse events, 15% view event, 10% search, 8% upcoming, 10% list users
- 5% user bookings, 12% create booking, 5% cancel booking
- 5% event stats, 3% popular events, 2% global stats

### B.1 Load Test
- **Purpose:** Simulate normal-to-peak traffic and verify system handles expected load.
- **Config:** Ramp 0→50 VUs (2min) → hold 50 (5min) → ramp down (1min). ~8 min total.
- **Thresholds:** p(95)<500ms, p(99)<1000ms, error rate <1%
- **Result:** PASSED
  - p(95) = 48ms, p(99) = 71ms, avg = 22.5ms
  - Error rate = 0%
  - Throughput = ~40 RPS
  - Bookings created = 2,301
- **Conclusion:** System handles 50 concurrent users comfortably. Latency stays very low — well within thresholds.

### B.2 Stress Test
- **Purpose:** Progressive overload to find degradation point.
- **Config:** Ramp 0→50 (1min) → 100 (2min) → 200 (2min) → 300 (2min) → 0 (1min). ~8 min total.
- **Thresholds:** p(95)<1500ms, error rate <10%
- **Result:** PASSED
  - p(95) = 432ms
  - Error rate = 1.22% (564 requests hit 60s timeout at peak 200-300 VUs)
  - Median = 194ms, avg = 963ms (average skewed by timeout outliers)
  - Throughput = ~90 RPS
  - Bookings: 5,491 success, 24 sold out, 76 failed
- **Key finding:** Graceful degradation — failure rate is uniform (~2%) across all endpoints, indicating connection-level exhaustion rather than any specific slow endpoint.
- **Note:** API container became unresponsive after test. Required `docker compose restart api`. Prometheus target showed DOWN.

### B.3 Spike Test
- **Purpose:** Test system response to sudden traffic burst and recovery after spike.
- **Config:** 0→10 (30s) → hold 10 (1min) → spike 10→300 (10s) → hold 300 (30s) → drop 300→10 (10s) → hold 10 (1min) → 0. ~3.5 min total.
- **Thresholds:** p(95)<2000ms, error rate <15%
- **Result:** FAILED (p95 threshold crossed)
  - p(95) = 59.99s (60s timeout)
  - Error rate = 7.99% (passed <15% threshold)
  - Median = 27ms, avg = 5.45s
  - Throughput = ~13 RPS (severely degraded)
  - For successful responses only: p(95) = 439ms
  - Bookings: 345 success, 3 sold out, 21 failed
- **Key finding:** Single worker cannot handle sudden 10→300 VU spike. Requests pile up faster than the worker can drain them, causing cascading 60s timeouts. Gradual ramp (stress test at same VU count) works because the worker has time to process the queue between stages. This is the strongest case for multi-worker deployment.
- **Comparison with stress test:** Same 300 VUs, but gradual ramp achieves p(95)=432ms and 90 RPS vs spike's p(95)=60s and 13 RPS.
- **Note:** API container crashed after test.

### B.4 Soak Test
- **Purpose:** Long-running stability test to detect memory leaks, connection pool exhaustion, or latency creep.
- **Config:** Ramp 0→30 (1min) → hold 30 (30min) → ramp down (1min). ~32 min total.
- **Thresholds:** p(95)<700ms, error rate <1%
- **Result:** PASSED
  - p(95) = 44ms
  - Error rate = 0.00%
  - Median = 17.5ms, avg = 23.4ms, max = 12.58s (single outlier)
  - Throughput = ~12 RPS
  - Checks = 100% (23,213/23,213)
  - Bookings created = 2,815
  - 0 interrupted iterations
- **Key finding:** No memory leaks, no connection pool exhaustion, no latency creep. System is completely stable under sustained 30 VU load for 32 minutes. Flat latency curve throughout.

### B.5 Breakpoint Test
- **Purpose:** Find absolute maximum capacity using open-model load (requests arrive regardless of response time).
- **Config:** ramping-arrival-rate executor, 10→500 RPS over 20 min. preAllocatedVUs=50, maxVUs=500. abortOnFail when p(95)>5000ms.
- **Result:** ABORTED at ~2 min (by design — breakpoint found)
  - p(95) = 30.45s (crossed 5s abort threshold)
  - Error rate = 3.22%
  - Actual throughput = ~11 RPS, target at abort = ~25 iters/s
  - VUs allocated = 456/457 (maxVUs nearly exhausted)
  - Dropped iterations = 409 (K6 couldn't generate requests fast enough)
  - Bookings created = 144
- **Key finding:** Single worker breakpoint is ~25-30 target RPS under open-model load. Open model is harsher than closed model (stress test's 90 RPS) because new requests keep arriving regardless of whether previous ones completed. This is more representative of real-world traffic patterns where users don't wait for each other.
- **Note:** API container crashed.

---

## Phase C — Targeted Scenarios

### C.1 Contention Test
- **Purpose:** Test row-level locking (`with_for_update()`) under extreme contention — 50 VUs all booking the same event simultaneously.
- **Config:** 50 VUs, 2 min, all targeting event_id=1. Custom metrics for booking latency.
- **Thresholds:** booking latency p(95)<3000ms, error rate <5%
- **Result:** PASSED
  - Booking latency p(95) = 148ms
  - HTTP p(95) = 122ms, avg = 49ms, max = 850ms
  - Error rate = 0.00%
  - Checks = 100% (20,054/20,054)
  - Throughput = ~166 RPS
  - Bookings success = 283, sold out (409) = 9,744
- **Key finding:** `with_for_update()` row locking handles contention perfectly. 50 concurrent VUs on the same event produced correct behavior: limited bookings succeeded (283, constrained by ticket capacity), then all subsequent attempts got 409 sold-out responses. Zero errors, zero deadlocks, low latency despite heavy lock contention.

### C.2 Read vs Write Test
- **Purpose:** Compare system behavior under read-heavy vs write-heavy traffic to measure how write locks affect overall performance.
- **Config:** Two sequential scenarios at 30 VUs, 3 min each:
  - `read_heavy`: 90% reads / 10% writes
  - `write_heavy`: 40% reads / 60% writes
- **Thresholds:** read_heavy p(95)<500ms, write_heavy p(95)<1500ms, error rate <5%
- **Result:** PASSED

| Profile | p(95) | Median | Avg | Max |
|---------|-------|--------|-----|-----|
| Read-heavy (90/10) | 77ms | 26ms | 33ms | 251ms |
| Write-heavy (40/60) | 130ms | 31ms | 49ms | 15.28s |

  - Error rate = 0.00% across both scenarios
  - Checks = 100% (19,205/19,205)
  - Bookings: 1,009 (read-heavy) + 3,264 (write-heavy)
  - Throughput = ~52 RPS combined
- **Key finding:** Write-heavy traffic is ~1.7x slower at p(95) (130ms vs 77ms). Write operations require row locks (`with_for_update()`), transaction commits, and capacity validation, whereas reads are simple SELECT queries. The max response time under write-heavy (15.28s) suggests occasional lock contention spikes. However, the overall difference is modest — the system handles both profiles with zero errors.

---

## Known Issues — 1 Worker

| Issue | When | Impact |
|-------|------|--------|
| API container crashes | After stress test (300 VUs) and spike test (300 VUs) | Requires `docker compose restart api` |
| Prometheus target DOWN | After API crash | "context deadline exceeded" — resolves after restart |
| Single event loop saturation | At 200+ concurrent VUs | Worker can't recover from accumulated request backlog |

**Root cause:** Single Uvicorn worker runs one Python event loop. When concurrent connections exceed what the loop can process, requests queue up, timeouts cascade, and the worker becomes unresponsive. This is a fundamental single-process limitation.

---

## Key Takeaways — 1 Worker

1. **Low-to-moderate load (10-50 VUs):** Excellent performance. p(95) stays under 62ms with 0% errors.
2. **High load (200-300 VUs):** System degrades gracefully under gradual ramp (stress: p95=432ms) but collapses under sudden spike (p95=60s).
3. **Stability:** Perfect over long duration — 32-minute soak test showed zero degradation.
4. **Concurrency control:** `with_for_update()` row locking works flawlessly even under extreme contention (50 VUs, same event).
5. **Read vs Write:** Write-heavy traffic is ~1.7x slower at p(95) but still performs well.
6. **Breakpoint:** Maximum sustainable throughput is ~25-30 RPS under open-model load, ~90 RPS under closed-model.
7. **Recovery:** API container needs manual restart after high-VU tests — single worker can't self-recover from event loop saturation.
