# Diplomski Projekt — Performance Testing of a REST API

## Quick Start

### 1. Configure environment
```bash
cp .env.example .env    # edit WORKERS=1 (or 2, 4) as needed
```

### 2. Start all services
```bash
docker compose up --build -d
docker compose ps       # verify all services are healthy
```

### 3. Seed the database
```bash
docker compose exec api python seed_data.py --reset
```

### Service URLs
| Service | URL |
|---------|-----|
| API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin) |

---

## Running Performance Tests

### Run all tests (recommended)
Git Bash:
```bash
./run_tests.sh
```

PowerShell (VS Code terminal):
```powershell
& "C:\Program Files\Git\bin\bash.exe" ./run_tests.sh
```

This automatically handles re-seeding, API restarts after crashes, cool-down periods, and result saving.

### Run specific tests
```bash
./run_tests.sh baseline load stress
```

### Run a single test manually (PowerShell)
```powershell
docker compose exec api python seed_data.py --reset
$env:K6_PROMETHEUS_RW_SERVER_URL="http://localhost:9090/api/v1/write"
$env:K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max"
k6 run --out experimental-prometheus-rw tests/load_test.js
```

### Available tests
| Test | File | Duration |
|------|------|----------|
| Baseline | `tests/baseline_test.js` | 30s |
| Endpoint Benchmark | `tests/endpoint_benchmark_test.js` | ~6 min |
| Load | `tests/load_test.js` | ~8 min |
| Stress | `tests/stress_test.js` | ~8 min |
| Spike | `tests/spike_test.js` | ~3.5 min |
| Soak | `tests/soak_test.js` | ~32 min |
| Breakpoint | `tests/breakpoint_test.js` | ~20 min |
| Contention | `tests/contention_test.js` | 2 min |
| Read vs Write | `tests/read_vs_write_test.js` | ~6 min |

---

## Switching Worker Configurations

Edit `.env`:
```
WORKERS=4
```

Then restart (no rebuild needed):
```bash
docker compose up -d
```

Run tests for that configuration:
```bash
./run_tests.sh
```

Results are automatically saved to `results/1w/`, `results/2w/`, or `results/4w/`.

---

## Viewing Results in Grafana

1. Open http://localhost:3000 (login: admin/admin)
2. Go to Dashboards → K6 → **K6 Performance Test Results**
3. Use the **testid** dropdown to filter by test type
4. Set time range to cover your test duration

---

## Remote Server Testing

To test against a remote API:
```bash
k6 run -e BASE_URL=http://your-server:8000 tests/load_test.js
```

---

## Resource Limits

All containers have fixed resource limits to ensure reproducible results:

| Service | CPU | Memory |
|---------|-----|--------|
| API | 2.0 | 1 GB |
| PostgreSQL | 2.0 | 1 GB |
| Prometheus | 1.0 | 512 MB |
| Grafana | 0.5 | 256 MB |
| Node Exporter | 0.25 | 128 MB |

These limits stay **constant** across all worker configurations (1w, 2w, 4w). Only the `WORKERS` variable changes.

---

## Documentation

See [DOCUMENTATION.md](DOCUMENTATION.md) for full project documentation.
