# Test Run History

Tracks key results across multiple test iterations to identify consistency and variance in scaling patterns.

**Configuration:** Docker (FastAPI + PostgreSQL), 4 CPU / 2 GB API, 3 CPU / 2 GB DB
**Pool formula:** `pool_size = max(5, 60 // WORKERS)`, `max_overflow = max(5, 30 // WORKERS)`

---

## Run 1 — 2026-04-08

**Pattern observed: U-curve (2w worst under high load)**

2w collapsed in breakpoint (30,686ms p95, 6.7% errors, 69K dropped iterations) while 1w and 4w both completed cleanly at 189 RPS with 0% errors. Stress test also showed 2w underperforming both 1w and 4w. Low-load tests (load, soak) were identical across all configs (~28ms p95).

| Test | 1w p95 | 1w RPS | 1w Err | 2w p95 | 2w RPS | 2w Err | 4w p95 | 4w RPS | 4w Err |
|------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| Stress | 151ms | 251 | 0% | 529ms | 178 | 0.14% | 129ms | 255 | 0% |
| Breakpoint | 192ms | 189 | 0% | 30,686ms | 42 | 6.7% | 106ms | 189 | 0% |
| Spike | 525ms | 102 | 0% | 658ms | 80 | 0% | 155ms | 117 | 0% |
| Recovery | 521ms | 93 | 0% | 465ms | 86 | 0% | 137ms | 103 | 0% |

---

## Run 2 — 2026-04-09

**Pattern observed: Roughly linear (1w worst, 4w best under sustained load)**

U-curve did NOT reproduce. 1w collapsed in breakpoint (1,464ms p95, 4.6% errors, 149K dropped) while 2w and 4w handled it well. Stress showed clear linear scaling: 4w (177ms) > 2w (262ms) > 1w (886ms). Interestingly, 2w outperformed 4w in spike (289ms vs 609ms) and recovery (277ms vs 539ms), suggesting burst-handling varies by run.

| Test | 1w p95 | 1w RPS | 1w Err | 2w p95 | 2w RPS | 2w Err | 4w p95 | 4w RPS | 4w Err |
|------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| Stress | 886ms | 164 | 0% | 262ms | 230 | 0% | 177ms | 248 | 0% |
| Breakpoint | 1,464ms | 62 | 4.6% | 247ms | 183 | 0.14% | 112ms | 189 | 0% |
| Spike | 1,225ms | 62 | 0% | 289ms | 104 | 0% | 609ms | 98 | 0% |
| Recovery | 938ms | 72 | 0% | 277ms | 95 | 0% | 539ms | 92 | 0% |

---

## Key Observations Across Runs

1. **Low-load tests are deterministic** — Load (~28ms), soak (~27ms), contention (283 bookings) produce nearly identical results across all runs and configs.
2. **High-load tests are variable** — Stress, breakpoint, spike, and recovery show significant variance between runs for the same config.
3. **Neither U-curve nor linear scaling is definitive** — Run 1 showed 2w as worst; Run 2 showed 1w as worst. More runs needed to establish the true pattern.
4. **4w is consistently the best under sustained load** — Both runs show 4w with the lowest breakpoint latency and highest RPS.
5. **Additional runs planned** to determine whether Run 1's U-curve or Run 2's linear pattern is more representative.
