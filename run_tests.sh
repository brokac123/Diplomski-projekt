#!/bin/bash
# =============================================================================
# Performance Test Runner
# Usage:
#   ./run_tests.sh              — run all tests for current WORKERS config
#   ./run_tests.sh load         — run only load test
#   ./run_tests.sh load stress  — run load and stress tests
# =============================================================================

set -e

# --- Configuration ---
PROMETHEUS_URL="http://localhost:9090/api/v1/write"
TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max"

# Read WORKERS from .env file (default: 1)
if [ -f .env ]; then
  WORKERS=$(grep -E "^WORKERS=" .env | cut -d'=' -f2 | tr -d ' ')
fi
WORKERS="${WORKERS:-1}"
WORKERS_LABEL="${WORKERS}w"

# Ordered test list — each builds on insights from the previous
ALL_TESTS=(
  baseline
  endpoint_benchmark
  load
  stress
  spike
  soak
  breakpoint
  contention
  read_vs_write
)

# Tests that need re-seeding before running
NEEDS_RESEED=(baseline endpoint_benchmark load stress spike soak breakpoint contention read_vs_write)

# Tests that may crash the API (need restart + health check after)
MAY_CRASH=(stress spike breakpoint)

# Map test names to files
declare -A TEST_FILES
TEST_FILES[baseline]="tests/baseline_test.js"
TEST_FILES[endpoint_benchmark]="tests/endpoint_benchmark_test.js"
TEST_FILES[load]="tests/load_test.js"
TEST_FILES[stress]="tests/stress_test.js"
TEST_FILES[spike]="tests/spike_test.js"
TEST_FILES[soak]="tests/soak_test.js"
TEST_FILES[breakpoint]="tests/breakpoint_test.js"
TEST_FILES[contention]="tests/contention_test.js"
TEST_FILES[read_vs_write]="tests/read_vs_write_test.js"

# --- Helper Functions ---

reseed() {
  echo ""
  echo "=== Re-seeding database ==="
  docker compose exec -T api python seed_data.py --reset
  echo "Waiting 10s for DB to stabilize..."
  sleep 10
}

restart_api() {
  echo ""
  echo "=== Restarting API (post-crash recovery) ==="
  docker compose restart api
  echo "Waiting 20s for API to be healthy..."
  sleep 20

  # Verify API is actually healthy
  local retries=5
  for i in $(seq 1 $retries); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
      echo "API is healthy."
      return 0
    fi
    echo "API not ready, retry $i/$retries..."
    sleep 5
  done
  echo "ERROR: API did not recover after restart!"
  return 1
}

contains() {
  local value="$1"
  shift
  for item in "$@"; do
    if [ "$item" = "$value" ]; then
      return 0
    fi
  done
  return 1
}

run_test() {
  local test_name="$1"
  local test_file="${TEST_FILES[$test_name]}"

  if [ -z "$test_file" ]; then
    echo "ERROR: Unknown test '$test_name'"
    echo "Available: ${ALL_TESTS[*]}"
    return 1
  fi

  echo ""
  echo "================================================================"
  echo "  TEST: $test_name ($WORKERS_LABEL)"
  echo "  File: $test_file"
  echo "  Time: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "================================================================"

  # Re-seed if needed
  if contains "$test_name" "${NEEDS_RESEED[@]}"; then
    reseed
  fi

  # Run the test
  K6_PROMETHEUS_RW_SERVER_URL="$PROMETHEUS_URL" \
  K6_PROMETHEUS_RW_TREND_STATS="$TREND_STATS" \
  k6 run --out experimental-prometheus-rw \
    -e WORKERS="$WORKERS_LABEL" \
    "$test_file"

  local exit_code=$?

  echo ""
  echo "--- $test_name finished (exit code: $exit_code) ---"

  # Restart API if this test may have crashed it
  if contains "$test_name" "${MAY_CRASH[@]}"; then
    restart_api
  fi

  # Cool-down between tests
  echo "Cooling down 30s before next test..."
  sleep 30

  return 0
}

# --- Main ---

echo "================================================================"
echo "  Performance Test Suite"
echo "  Workers: $WORKERS ($WORKERS_LABEL)"
echo "  Results: results/$WORKERS_LABEL/"
echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"

# Create results directory
mkdir -p "results/$WORKERS_LABEL"

# Verify services are running
echo ""
echo "Checking services..."
if ! curl -sf http://localhost:8000/health > /dev/null 2>&1; then
  echo "ERROR: API is not running. Start with: docker compose up -d"
  exit 1
fi
if ! curl -sf http://localhost:9090/-/ready > /dev/null 2>&1; then
  echo "ERROR: Prometheus is not running."
  exit 1
fi
echo "All services healthy."

# Determine which tests to run
if [ $# -gt 0 ]; then
  TESTS_TO_RUN=("$@")
else
  TESTS_TO_RUN=("${ALL_TESTS[@]}")
fi

# Run tests
PASSED=0
FAILED=0
for test_name in "${TESTS_TO_RUN[@]}"; do
  if run_test "$test_name"; then
    PASSED=$((PASSED + 1))
  else
    FAILED=$((FAILED + 1))
    echo "WARNING: $test_name had issues, continuing..."
  fi
done

echo ""
echo "================================================================"
echo "  DONE"
echo "  Workers: $WORKERS ($WORKERS_LABEL)"
echo "  Passed: $PASSED / $((PASSED + FAILED))"
echo "  Results: results/$WORKERS_LABEL/"
echo "  Finished: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"
