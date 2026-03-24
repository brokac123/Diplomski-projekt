# Diplomski Projekt — Booking API

## Running the Project

### Start all services
```bash
docker compose up --build -d
```

### Seed the database
```bash
# Fresh seed (keeps existing data)
docker compose exec api python seed_data.py

# Reset and re-seed
docker compose exec api python seed_data.py --reset
```

### Run K6 tests (once implemented)
```bash
k6 run tests/load_test.js
k6 run tests/stress_test.js
k6 run tests/spike_test.js
k6 run tests/soak_test.js
k6 run tests/breakpoint_test.js
```

### Check service health
```bash
docker compose ps
```

### View API logs
```bash
docker compose logs api
```

### Service URLs
| Service | URL |
|---------|-----|
| API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |
