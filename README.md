# Diplomski Projekt — Booking API

## Quick Start

### Start all services
```bash
docker compose up --build -d
```

### Seed the database
```bash
# Fresh seed (keeps existing data)
docker compose exec api python seed_data.py

# Reset and re-seed (recommended before each test)
docker compose exec api python seed_data.py --reset
```

### Check service health
```bash
docker compose ps
```

### Service URLs
| Service | URL |
|---------|-----|
| API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Prometheus Targets | http://localhost:9090/targets |
| Grafana | http://localhost:3000 (admin/admin) |

---

## Running Performance Tests

### Run a test with Grafana visualization (PowerShell)
```powershell
docker compose exec api python seed_data.py --reset
$env:K6_PROMETHEUS_RW_SERVER_URL="http://localhost:9090/api/v1/write"; $env:K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max"; k6 run --out experimental-prometheus-rw tests/<test_file>.js
```

### Run a test without Grafana (terminal results only)
```bash
k6 run tests/load_test.js
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
| Breakpoint | `tests/breakpoint_test.js` | ~2-20 min |
| Contention | `tests/contention_test.js` | 2 min |
| Read vs Write | `tests/read_vs_write_test.js` | ~6 min |

### After high-load tests (stress, spike, breakpoint)
```bash
docker compose restart api
```

---

## Viewing Results in Grafana

1. Open http://localhost:3000 (login: admin/admin)
2. Go to Dashboards → K6 → **K6 Performance Test Results**
3. Set time range to cover your test (e.g., "Last 15 minutes")
4. Set auto-refresh to 5s for live monitoring

---

## 4-Worker Mode

Uncomment the command line in `docker-compose.yml` under the `api` service:
```yaml
command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

Then rebuild:
```bash
docker compose up --build -d
```

---

## Documentation

See [documentation.md](documentation.md) for full project documentation including test explanations, metrics rationale, and architecture details.
