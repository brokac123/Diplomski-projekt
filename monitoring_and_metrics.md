# Monitoring, Metrics & Data Flow

This document explains the complete monitoring infrastructure of the project — how metrics are collected, stored, and displayed. It covers every component, every connection, and the full lifecycle of a metric from the moment a request is made to the moment it appears as a chart on the Grafana dashboard.

---

## Table of Contents

1. [Overview — The Four Components](#1-overview--the-four-components)
2. [K6 — The Test Runner and Metric Collector](#2-k6--the-test-runner-and-metric-collector)
3. [Prometheus — The Central Data Store](#3-prometheus--the-central-data-store)
4. [Grafana — The Visualization Layer](#4-grafana--the-visualization-layer)
5. [Node Exporter — System Resource Metrics](#5-node-exporter--system-resource-metrics)
6. [FastAPI /metrics Endpoint](#6-fastapi-metrics-endpoint)
7. [K6 Metrics In Detail](#7-k6-metrics-in-detail)
8. [Custom Metrics Defined In The Project](#8-custom-metrics-defined-in-the-project)
9. [How K6 Metrics Become Prometheus Metrics](#9-how-k6-metrics-become-prometheus-metrics)
10. [How Grafana Panels Query Prometheus](#10-how-grafana-panels-query-prometheus)
11. [End-to-End Lifecycle of a Metric](#11-end-to-end-lifecycle-of-a-metric)
12. [Two Data Flows — Push vs Pull](#12-two-data-flows--push-vs-pull)
13. [Dashboard Panels and Their Queries](#13-dashboard-panels-and-their-queries)
14. [Configuration Files — Where Everything Is Connected](#14-configuration-files--where-everything-is-connected)

---

## 1. Overview — The Four Components

The monitoring stack consists of four components, each with a distinct role:

| Component | Role | Port | Runs When |
|-----------|------|------|-----------|
| **K6** | Runs tests, collects performance metrics, pushes to Prometheus | N/A (runs on host) | Only during test execution |
| **Prometheus** | Central time-series database — stores all metrics | 9090 | 24/7 (Docker container) |
| **Grafana** | Queries Prometheus and renders dashboards | 3000 | 24/7 (Docker container) |
| **Node Exporter** | Collects CPU and memory metrics from the host system | 9100 | 24/7 (Docker container) |

Additionally, the **FastAPI API** itself exposes a `/metrics` endpoint for Prometheus to scrape, but this data is not used on the Grafana dashboard.

**Key principle:** Prometheus is the central hub. Every metric from every source ends up in Prometheus. Grafana only talks to Prometheus — it never communicates with K6, the API, or Node Exporter directly.

```
K6 (pushes) ──────────►
                         PROMETHEUS ◄────── Grafana (queries)
API + Node Exporter ───►  (stores)
   (Prometheus pulls)
```

---

## 2. K6 — The Test Runner and Metric Collector

K6 is a load testing tool that runs on the host machine (outside Docker). It has two jobs:

1. **Send HTTP requests** to the FastAPI application (simulating real users)
2. **Collect metrics** from every request it makes and push them to Prometheus

K6 is triggered manually via the command line or through `run_tests.sh`:

```bash
K6_PROMETHEUS_RW_SERVER_URL="http://localhost:9090/api/v1/write" \
K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max" \
k6 run --out experimental-prometheus-rw tests/stress_test.js
```

Breaking down this command:

- `K6_PROMETHEUS_RW_SERVER_URL` — tells K6 **where** to push metrics (Prometheus remote write endpoint)
- `K6_PROMETHEUS_RW_TREND_STATS` — tells K6 **which** percentile stats to compute and send
- `--out experimental-prometheus-rw` — activates K6's Prometheus Remote Write output plugin
- `tests/stress_test.js` — the test script to execute

Without `--out experimental-prometheus-rw`, K6 would still run the test and print results to the terminal, but no data would reach Prometheus or Grafana.

K6 does **not** have a `/metrics` endpoint. It pushes data directly to Prometheus via HTTP POST. This is called the **push model** — K6 initiates the data transfer, not Prometheus.

---

## 3. Prometheus — The Central Data Store

Prometheus is a time-series database. It does not generate metrics — it only **receives** and **stores** data from other sources.

Prometheus has zero metrics by default. Without configured sources, it would be an empty database. In this project, Prometheus receives data from three sources:

| Source | Transport Method | Frequency |
|--------|-----------------|-----------|
| K6 | K6 pushes via HTTP POST (remote write) | Every few seconds during tests |
| FastAPI `/metrics` | Prometheus pulls via HTTP GET (scrape) | Every 5 seconds, 24/7 |
| Node Exporter `/metrics` | Prometheus pulls via HTTP GET (scrape) | Every 5 seconds, 24/7 |

Prometheus stores each data point as a **time series** — a metric name, a set of labels, a value, and a timestamp:

```
k6_http_req_duration_p95{name="CreateBooking", testid="stress"} = 0.068 @ 14:23:20
k6_http_req_duration_p95{name="CreateBooking", testid="stress"} = 0.071 @ 14:23:25
k6_http_req_duration_p95{name="CreateBooking", testid="stress"} = 0.065 @ 14:23:30
```

Data is retained for 90 days (configured in `docker-compose.yml` with `--storage.tsdb.retention.time=90d`).

To accept K6's push data, Prometheus must have remote write receiving enabled. This is configured in `docker-compose.yml`:

```yaml
command:
  - '--web.enable-remote-write-receiver'
```

Without this flag, Prometheus would reject K6's HTTP POST requests.

---

## 4. Grafana — The Visualization Layer

Grafana is purely a visualization tool. It does not collect, store, or process any metrics. It only:

1. **Queries** Prometheus using PromQL (Prometheus Query Language)
2. **Renders** the results as charts, graphs, gauges, and stat panels

Grafana connects to Prometheus via a configured **datasource**. This is defined in `monitoring/grafana/provisioning/datasources.yml`:

```yaml
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

The `url: http://prometheus:9090` is how Grafana knows where to send queries. This uses Docker's internal DNS — all containers in the same `docker-compose.yml` can reach each other by service name.

When you open a dashboard, each panel sends a PromQL query to `http://prometheus:9090/api/v1/query_range`. Prometheus returns the results, and Grafana draws the chart.

The dashboard layout and panel definitions are stored in `monitoring/grafana/dashboards/k6_results.json`. This is a **template file** — it defines what charts to show and what queries to run, but contains no actual data. The data always comes from Prometheus at query time.

---

## 5. Node Exporter — System Resource Metrics

Node Exporter is a pre-built Prometheus exporter that collects host-level system metrics — CPU usage, memory usage, disk I/O, network statistics, etc. It runs as a Docker container and exposes metrics at `http://node-exporter:9100/metrics`.

Node Exporter requires no configuration. It automatically reads system information from the Linux kernel and formats it for Prometheus.

In this project (running on Windows with Docker via WSL2), Node Exporter monitors the WSL2 virtual machine that Docker runs inside — not the Windows host directly.

Prometheus scrapes Node Exporter every 5 seconds, as configured in `monitoring/prometheus.yml`:

```yaml
- job_name: "node"
  static_configs:
    - targets: ["node-exporter:9100"]
```

Key metrics from Node Exporter used on the dashboard:

| Metric | What It Measures |
|--------|-----------------|
| `node_cpu_seconds_total` | CPU time spent per mode (idle, user, system) |
| `node_memory_MemTotal_bytes` | Total system RAM |
| `node_memory_MemAvailable_bytes` | Available (unused) RAM |

---

## 6. FastAPI /metrics Endpoint

The FastAPI application exposes a `/metrics` endpoint that Prometheus scrapes. This is created by a single line in `app/main.py`:

```python
Instrumentator().instrument(app).expose(app)
```

This line does two things:

1. `.instrument(app)` — automatically tracks every HTTP request the API receives (count, duration, status code, method, path)
2. `.expose(app)` — registers a `/metrics` route that returns all tracked data in Prometheus text format

If you visit `http://localhost:8000/metrics` in a browser, you would see raw text like:

```
http_requests_total{method="GET", handler="/users/", status="200"} 4523
http_request_duration_seconds_sum{method="GET", handler="/events/"} 12.847
http_request_duration_seconds_count{method="GET", handler="/events/"} 892
```

Prometheus scrapes this endpoint every 5 seconds, as configured in `monitoring/prometheus.yml`:

```yaml
- job_name: "fastapi"
  metrics_path: /metrics
  static_configs:
    - targets: ["api:8000"]
```

**Important:** This scrape runs 24/7, regardless of whether K6 tests are running. It captures all requests the API receives — including those from K6 tests, manual browser requests, or health checks.

**The Grafana dashboard does not use these metrics.** K6 metrics are used instead because they provide more detail — per-endpoint tagging via the `name` field, custom business metrics (booking success/fail/sold out), and precise percentile calculations. The FastAPI `/metrics` data is available in Prometheus for ad-hoc queries but is not visualized on the dashboard.

---

## 7. K6 Metrics In Detail

K6 has two categories of metrics: **built-in** (automatic) and **custom** (defined by you in test code).

### Built-in Metrics

These are created automatically by K6 for every HTTP request. You never define or import them — they exist because you use `http.get()` or `http.post()`:

| K6 Metric | Type | What It Measures | When It's Created |
|-----------|------|-----------------|-------------------|
| `http_reqs` | Counter | Total number of HTTP requests made | Every `http.get()` or `http.post()` call |
| `http_req_duration` | Trend | End-to-end request duration (ms) | Every `http.get()` or `http.post()` call |
| `http_req_failed` | Rate | Ratio of failed requests (0.0 - 1.0) | Every `http.get()` or `http.post()` call |
| `vus` | Gauge | Number of currently active virtual users | Continuously by K6 runner |
| `vus_max` | Gauge | Maximum VUs allocated | Continuously by K6 runner |
| `iterations` | Counter | Number of times the default function completed | Each time a VU finishes one loop |

If you search your project code for `http_req_duration` or `http_reqs`, you will not find them defined anywhere. They are internal to the K6 binary.

### K6 Metric Types

K6 has four metric types:

| Type | Behavior | Example |
|------|----------|---------|
| **Counter** | Only increments (goes up) | `http_reqs`: 0 → 1 → 2 → 3 → ... |
| **Rate** | Tracks true/false ratio | `http_req_failed`: 0.015 (1.5% failed) |
| **Gauge** | Current value (goes up and down) | `vus`: 10 → 50 → 300 → 50 → 10 |
| **Trend** | Records individual values, computes percentiles | `http_req_duration`: stores each request's duration, calculates p50/p90/p95/p99/avg/min/max |

### Tags — How Metrics Get Labeled

Every HTTP request in K6 test code includes a `tags` object:

```javascript
http.get(`${BASE_URL}/events/?limit=20`, { tags: { name: "BrowseEvents" } });
```

Each test also has a global `testid` tag in its options:

```javascript
tags: { testid: "stress" },
```

These tags become **labels** in Prometheus. A single request generates metrics like:

```
k6_http_req_duration_p95{name="BrowseEvents", testid="stress"} = 0.031
```

Tags are what allow Grafana to:
- Filter by test type (using `testid`)
- Show per-endpoint breakdowns (using `name`)
- Display separate lines for each endpoint on a chart

If you added a new endpoint to a test with `{ tags: { name: "NewEndpoint" } }`, it would automatically appear on the Grafana dashboard — no dashboard changes needed.

---

## 8. Custom Metrics Defined In The Project

Custom metrics are metrics you define explicitly in test code because K6's built-in metrics don't cover your specific needs. K6 doesn't know what a "booking" is — so you create metrics to track business-level outcomes.

### In `tests/realistic_test.js` (lines 29-32):

```javascript
import { Counter } from "k6/metrics";

export const bookingSuccess = new Counter("booking_success");
export const bookingFail = new Counter("booking_fail");
export const bookingSoldOut = new Counter("booking_sold_out");
```

Used when a booking request completes (lines 95-101):

```javascript
if (res.status === 200) {
  bookingSuccess.add(1);       // successful booking
} else if (res.status === 409) {
  bookingSoldOut.add(1);       // event sold out (expected)
} else {
  bookingFail.add(1);          // actual error
}
```

**Purpose:** K6's built-in `http_req_failed` only tells you "a request failed." It cannot distinguish between a 409 (sold out — expected and correct behavior) and a 500 (server error — actual problem). These custom counters separate business outcomes from technical failures.

These counters are exported and reused by all Phase B tests (load, stress, spike, soak, breakpoint, recovery) via import.

### In `tests/contention_test.js` (lines 22-25):

```javascript
import { Counter, Trend } from "k6/metrics";

const contentionBookingSuccess = new Counter("contention_booking_success");
const contentionBookingSoldOut = new Counter("contention_booking_sold_out");
const contentionBookingLatency = new Trend("contention_booking_latency");
```

The `Trend` type is different from `Counter`. It records individual values and K6 computes percentiles from them. Used at line 70:

```javascript
contentionBookingLatency.add(res.timings.duration);
```

This records the exact duration of each booking request under contention. In Prometheus, this becomes multiple metrics: `k6_contention_booking_latency_p50`, `_p90`, `_p95`, `_p99`, `_avg`, `_min`, `_max`.

### In `tests/read_vs_write_test.js` (lines 21-22):

```javascript
const readHeavyBookings = new Counter("read_heavy_bookings");
const writeHeavyBookings = new Counter("write_heavy_bookings");
```

**Purpose:** Tracks how many bookings were created in each scenario (read-heavy vs write-heavy) to compare write throughput under different workload ratios.

### Summary of All Custom Metrics

| Metric Name | Type | Defined In | Purpose |
|-------------|------|-----------|---------|
| `booking_success` | Counter | `realistic_test.js` | Successful booking creations |
| `booking_fail` | Counter | `realistic_test.js` | Failed booking attempts (errors) |
| `booking_sold_out` | Counter | `realistic_test.js` | Sold-out responses (409 — expected) |
| `contention_booking_success` | Counter | `contention_test.js` | Successful bookings under contention |
| `contention_booking_sold_out` | Counter | `contention_test.js` | Sold-out responses under contention |
| `contention_booking_latency` | Trend | `contention_test.js` | Booking request duration under contention |
| `read_heavy_bookings` | Counter | `read_vs_write_test.js` | Bookings created in read-heavy scenario |
| `write_heavy_bookings` | Counter | `read_vs_write_test.js` | Bookings created in write-heavy scenario |

---

## 9. How K6 Metrics Become Prometheus Metrics

When K6 pushes metrics to Prometheus, the `experimental-prometheus-rw` plugin inside K6 **renames** them to follow Prometheus naming conventions. This renaming happens inside K6 before sending — Prometheus receives them already renamed.

### Renaming Rules

| K6 Type | K6 Internal Name | Prometheus Name | Rule Applied |
|---------|-----------------|-----------------|-------------|
| Counter | `http_reqs` | `k6_http_reqs_total` | Add `k6_` prefix + `_total` suffix |
| Counter | `booking_success` | `k6_booking_success_total` | Add `k6_` prefix + `_total` suffix |
| Rate | `http_req_failed` | `k6_http_req_failed_rate` | Add `k6_` prefix + `_rate` suffix |
| Gauge | `vus` | `k6_vus` | Add `k6_` prefix only |
| Trend | `http_req_duration` | `k6_http_req_duration_p50` | Add `k6_` prefix + split into one metric per stat |
| | | `k6_http_req_duration_p90` | |
| | | `k6_http_req_duration_p95` | |
| | | `k6_http_req_duration_p99` | |
| | | `k6_http_req_duration_avg` | |
| | | `k6_http_req_duration_min` | |
| | | `k6_http_req_duration_max` | |

**Trend splitting:** A single K6 Trend metric becomes 7 separate Prometheus metrics — one for each stat configured in `K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max"`. If you removed `p(99)` from that list, `k6_http_req_duration_p99` would not exist in Prometheus.

**Tags become labels:**

```javascript
// In test code:
http.get(url, { tags: { name: "BrowseEvents" } });
// With test options:
tags: { testid: "stress" }

// Becomes in Prometheus:
k6_http_reqs_total{name="BrowseEvents", testid="stress"} = 8241
```

### Duration Values

K6 sends duration values in **seconds** (e.g., 0.045 = 45ms). Grafana dashboard panels multiply by 1000 to display in milliseconds:

```
max(k6_http_req_duration_p95{testid=~"$testid"}) * 1000
```

---

## 10. How Grafana Panels Query Prometheus

Each panel in the Grafana dashboard is defined in `monitoring/grafana/dashboards/k6_results.json`. Every panel has a `targets` array containing one or more PromQL queries.

When you open the dashboard:

1. Grafana reads the panel template from `k6_results.json`
2. For each panel, Grafana sends the PromQL query to `http://prometheus:9090/api/v1/query_range`
3. Prometheus searches its database and returns matching data points
4. Grafana renders the chart

### Example: "Requests Per Second" Panel

Panel definition in `k6_results.json`:

```json
{
  "title": "Requests Per Second (RPS)",
  "type": "timeseries",
  "targets": [
    {
      "expr": "sum(rate(k6_http_reqs_total{testid=~\"$testid\"}[5s]))",
      "legendFormat": "Total RPS"
    }
  ]
}
```

Breaking down the PromQL query:

- `k6_http_reqs_total` — the raw counter metric (always increasing: 1, 2, 3, ...)
- `{testid=~"$testid"}` — filter by test type (`$testid` is a dashboard dropdown variable)
- `rate(...[5s])` — convert the counter into a per-second rate over 5-second windows
- `sum(...)` — add up all endpoints into one total number

Grafana sends this query to Prometheus, which returns values like:

```
14:23:15 → 82.3 req/s
14:23:20 → 85.1 req/s
14:23:25 → 79.8 req/s
```

Grafana plots these as a line chart: X axis = time, Y axis = requests per second.

### The `$testid` Variable

The dashboard has a dropdown at the top that lets you filter by test type. This is a **template variable** called `testid`. When you select "stress", every panel's query replaces `$testid` with `"stress"`, so only stress test data is shown.

This works because every test tags its metrics with a `testid`:

```javascript
// In stress_test.js options:
tags: { testid: "stress" }

// In load_test.js options:
tags: { testid: "load" }
```

---

## 11. End-to-End Lifecycle of a Metric

Here is the complete journey of a single metric from request to chart:

### Step 1: VU Makes a Request

K6 is running the stress test with 200 VUs. VU #47 calls `trafficMix()`, random selection picks "CreateBooking":

```javascript
let res = http.post(`${BASE_URL}/bookings/`, payload, {
  ...JSON_HEADERS,
  tags: { name: "CreateBooking" },
});
```

K6 sends a real HTTP POST to `http://localhost:8000/bookings/`.

### Step 2: FastAPI Processes It

FastAPI receives the request, runs the `create_booking()` function which executes `SELECT FOR UPDATE` on PostgreSQL, creates the booking row, returns HTTP 200 with the booking JSON. Total processing time: 41ms.

### Step 3: K6 Records the Measurement

K6 internally saves a raw data point:

```
timestamp: 14:23:17.482
duration: 41ms
status: 200
failed: false
tags: { name: "CreateBooking", testid: "stress" }
```

This happens for every request from every VU — hundreds of measurements per second.

### Step 4: Custom Metric Code Runs

Your code in `realistic_test.js` executes:

```javascript
if (res.status === 200) {
  bookingSuccess.add(1);
}
```

K6 internally increments the `booking_success` counter from 456 to 457.

### Step 5: K6 Aggregates (Every ~5 Seconds)

K6 takes all raw measurements collected since the last push and computes aggregates:

For `http_req_duration` with tag `name="CreateBooking"`:
- Sorts all durations from the interval
- Calculates: p50=35ms, p90=52ms, p95=68ms, p99=94ms, avg=38ms, min=12ms, max=112ms

For counters:
- `http_reqs{name="CreateBooking"}`: total = 3847
- `booking_success`: total = 457

For gauges:
- `vus`: current = 200

### Step 6: K6 Pushes to Prometheus

K6 renames metrics and sends an HTTP POST to `http://localhost:9090/api/v1/write`:

```
k6_http_req_duration_p50{name="CreateBooking", testid="stress"} = 0.035
k6_http_req_duration_p95{name="CreateBooking", testid="stress"} = 0.068
k6_http_req_duration_p50{name="BrowseEvents", testid="stress"} = 0.018
k6_http_req_duration_p95{name="BrowseEvents", testid="stress"} = 0.031
k6_http_reqs_total{name="CreateBooking", testid="stress"} = 3847
k6_http_reqs_total{name="BrowseEvents", testid="stress"} = 8241
k6_booking_success_total{testid="stress"} = 457
k6_http_req_failed_rate{testid="stress"} = 0.015
k6_vus{testid="stress"} = 200
```

K6 keeps pushing every few seconds for the entire test duration.

### Step 7: Prometheus Stores It

Prometheus appends each value with a timestamp to its time-series database:

```
k6_http_req_duration_p95{name="CreateBooking", testid="stress"}:
  14:23:15 → 0.062
  14:23:20 → 0.068
  14:23:25 → 0.071
  14:23:30 → 0.065
```

### Step 8: Test Ends

K6 stops VUs, sends the final push, prints results to terminal, saves JSON to `results/`, and exits. No more K6 data flows to Prometheus. The stored data remains for 90 days.

### Step 9: You Open Grafana

You navigate to `http://localhost:3000`, open the K6 dashboard, set `testid` to "stress", set time range to cover the test window.

### Step 10: Panels Query Prometheus

The "Response Time Percentiles" panel sends:

```
max(k6_http_req_duration_p95{testid=~"stress"}) * 1000
```

Prometheus returns:

```
14:23:15 → 62ms
14:23:20 → 68ms
14:23:25 → 71ms
14:23:30 → 65ms
```

### Step 11: Grafana Renders the Chart

Grafana takes the data points and draws a line chart. X axis = time, Y axis = milliseconds. The line shows how p95 latency changed throughout the test.

---

## 12. Two Data Flows — Push vs Pull

There are two completely separate and independent data flows running in this project:

### Flow 1: Prometheus Scraping (PULL — Always Running)

```
FastAPI /metrics ◄──── Prometheus pulls every 5s (HTTP GET)
Node Exporter    ◄──── Prometheus pulls every 5s (HTTP GET)
```

- **Direction:** Prometheus initiates — goes and fetches data
- **When:** 24/7, every 5 seconds, whether tests are running or not
- **What:** API internal metrics (request counts, durations) + system metrics (CPU, RAM)
- **Configured in:** `monitoring/prometheus.yml` (scrape_configs section)

### Flow 2: K6 Remote Write (PUSH — Only During Tests)

```
K6 ─────► Prometheus (HTTP POST to /api/v1/write)
```

- **Direction:** K6 initiates — pushes data to Prometheus
- **When:** Only while a K6 test is running
- **What:** Test metrics (latencies, percentiles, error rates, VU count, custom counters)
- **Configured in:** `run_tests.sh` (environment variables) + `docker-compose.yml` (`--web.enable-remote-write-receiver`)

### No Collision

These two flows operate independently inside Prometheus. They don't interfere with each other because:

1. **Different metric names** — K6 metrics start with `k6_`, Node Exporter with `node_`, FastAPI with `http_`
2. **Different operations** — scraping is HTTP GET that Prometheus initiates; remote write is HTTP POST that K6 initiates
3. **Negligible load** — Prometheus is designed to handle thousands of sources; three is trivial

### No Direct K6-to-Grafana Connection

K6 does not communicate with Grafana. Grafana does not communicate with K6. Both only talk to Prometheus:

```
K6 ──pushes──► PROMETHEUS ◄──queries── Grafana
                    ▲
    scrapes ────────┘
    API + Node Exporter
```

---

## 13. Dashboard Panels and Their Queries

The Grafana dashboard "K6 Performance Test Results" is defined in `monitoring/grafana/dashboards/k6_results.json`. It contains 17 panels organized in four categories.

### Application Performance Metrics (from K6)

| Panel | PromQL Query | Data Source | What It Shows |
|-------|-------------|-------------|---------------|
| **Active Virtual Users** | `k6_vus{testid=~"$testid"}` | K6 push | Number of concurrent VUs over time |
| **Requests Per Second** | `sum(rate(k6_http_reqs_total{testid=~"$testid"}[5s]))` | K6 push | Total throughput (all endpoints combined) |
| **Response Time Percentiles** | `max(k6_http_req_duration_p50/p90/p95/p99{...}) * 1000` | K6 push | p50, p90, p95, p99 latency in ms (4 lines) |
| **Error Rate** | `avg(k6_http_req_failed_rate{testid=~"$testid"})` | K6 push | Percentage of failed requests |
| **RPS by Endpoint** | `sum by (name) (rate(k6_http_reqs_total{...}[5s]))` | K6 push | Per-endpoint throughput (one line per `name` tag) |
| **Response Time by Endpoint** | `k6_http_req_duration_p95{...} * 1000` | K6 push | Per-endpoint p95 latency |
| **Response Time vs VUs** | `k6_http_req_duration_p95 + k6_vus` | K6 push | Dual-axis: latency (left) vs VU count (right) |

### Business Metrics (from K6 Custom Counters)

| Panel | PromQL Query | Data Source | What It Shows |
|-------|-------------|-------------|---------------|
| **Booking Metrics** | `sum(k6_booking_success_total{...})` | K6 push (custom) | Total successful bookings |
| **Sold Out Responses** | `sum(k6_booking_sold_out_total{...})` | K6 push (custom) | Total 409 sold-out responses |
| **Failed Bookings** | `sum(k6_booking_fail_total{...})` | K6 push (custom) | Total booking errors |
| **HTTP Requests Total** | `sum(k6_http_reqs_total{...})` | K6 push | Total request volume |
| **Avg Response Time** | `avg(k6_http_req_duration_avg{...}) * 1000` | K6 push | Gauge showing current average latency |
| **Peak VUs** | `max_over_time(k6_vus{...}[1h])` | K6 push | Highest VU count reached |

### Correlation Panels

| Panel | PromQL Queries | Data Sources | What It Shows |
|-------|---------------|-------------|---------------|
| **Per-Endpoint p95 Over Time** | `k6_http_req_duration_p95{...} * 1000` | K6 push | Each endpoint's p95 as a time series |
| **CPU Usage vs p95 Latency** | `node_cpu... + k6_http_req_duration_p95 + k6_vus` | Node Exporter + K6 | CPU% (left axis) vs p95 + VUs (right axis) |

### System Resource Metrics (from Node Exporter)

| Panel | PromQL Query | Data Source | What It Shows |
|-------|-------------|-------------|---------------|
| **CPU Usage (%)** | `100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[30s])) * 100)` | Node Exporter scrape | Host CPU utilization |
| **Memory Usage** | `node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes` | Node Exporter scrape | Used vs total memory |

### How PromQL Works (Key Patterns)

- `rate(counter[5s])` — converts an always-increasing counter into a per-second rate over 5-second windows
- `sum(...)` — adds up all matching time series into one
- `sum by (name) (...)` — groups results by the `name` label (one result per endpoint)
- `max(...)` — takes the highest value across all matching series
- `max_over_time(metric[1h])` — finds the peak value in the last hour
- `{testid=~"$testid"}` — filters by the dashboard dropdown selection
- `* 1000` — converts seconds to milliseconds

---

## 14. Configuration Files — Where Everything Is Connected

### `docker-compose.yml` — Service Orchestration

Defines all containers and their connections:

- **Prometheus** service: enables remote write receiver (`--web.enable-remote-write-receiver`), mounts `prometheus.yml` config, sets 90-day retention
- **Grafana** service: mounts datasource config (connects to Prometheus), mounts dashboard provisioning config, mounts dashboard JSON files
- **Node Exporter** service: runs with default config, no customization
- **API** service: runs FastAPI with `Instrumentator()` exposing `/metrics`

### `monitoring/prometheus.yml` — Prometheus Scrape Configuration

Tells Prometheus what to scrape and how often:

```yaml
global:
  scrape_interval: 5s        # how often to pull from targets

scrape_configs:
  - job_name: "fastapi"       # scrape API metrics
    metrics_path: /metrics
    static_configs:
      - targets: ["api:8000"]

  - job_name: "node"          # scrape system metrics
    static_configs:
      - targets: ["node-exporter:9100"]
```

Note: K6 remote write is NOT configured here. It's enabled via the `--web.enable-remote-write-receiver` flag in `docker-compose.yml` and triggered by K6's environment variables at runtime.

### `monitoring/grafana/provisioning/datasources.yml` — Grafana-to-Prometheus Connection

```yaml
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090    # where Grafana sends queries
    isDefault: true
```

### `monitoring/grafana/provisioning/dashboards.yml` — Dashboard Auto-Loading

```yaml
providers:
  - name: "K6 Dashboards"
    folder: "K6"
    type: file
    options:
      path: /var/lib/grafana/dashboards    # directory containing JSON dashboard files
```

### `monitoring/grafana/dashboards/k6_results.json` — Dashboard Template

Contains all 17 panel definitions with their PromQL queries, chart types, colors, axes, and layout positions. This is a template — it defines the structure, not the data.

### `run_tests.sh` — K6-to-Prometheus Connection

```bash
PROMETHEUS_URL="http://localhost:9090/api/v1/write"
TREND_STATS="p(50),p(90),p(95),p(99),avg,min,max"

K6_PROMETHEUS_RW_SERVER_URL="$PROMETHEUS_URL" \
K6_PROMETHEUS_RW_TREND_STATS="$TREND_STATS" \
k6 run --out experimental-prometheus-rw tests/stress_test.js
```

### `app/main.py` (line 14) — FastAPI Metrics Endpoint

```python
Instrumentator().instrument(app).expose(app)
```

Creates the `/metrics` endpoint that Prometheus scrapes.

---

## Complete Architecture Diagram

```
YOUR MACHINE (Windows / WSL2)
│
│  You run: k6 run --out experimental-prometheus-rw tests/stress_test.js
│
│  K6 (runs on host, outside Docker)
│  ├── Spawns VUs
│  ├── Sends real HTTP requests to FastAPI
│  ├── Records duration, status, tags for every request
│  ├── Records custom metrics (bookingSuccess.add(1))
│  ├── Aggregates every ~5 seconds (computes p50, p90, p95, p99, avg, min, max)
│  ├── Renames metrics (k6_ prefix, _total/_rate suffixes)
│  └── Pushes via HTTP POST to Prometheus /api/v1/write
│
│
│  DOCKER NETWORK
│  ┌─────────────────────────────────────────────────────────────┐
│  │                                                             │
│  │  FastAPI API (port 8000)                                    │
│  │  ├── Processes K6 requests (the actual load test)           │
│  │  ├── Instrumentator().expose(app) creates /metrics          │
│  │  └── /metrics scraped by Prometheus every 5s                │
│  │       (data available but NOT used on Grafana dashboard)    │
│  │                                                             │
│  │  Node Exporter (port 9100)                                  │
│  │  ├── Collects CPU, memory from Linux kernel                 │
│  │  └── /metrics scraped by Prometheus every 5s                │
│  │       (used for CPU and Memory panels on dashboard)         │
│  │                                                             │
│  │  Prometheus (port 9090)                                     │
│  │  ├── Receives K6 push data (remote write)                   │
│  │  ├── Scrapes API /metrics every 5s                          │
│  │  ├── Scrapes Node Exporter /metrics every 5s                │
│  │  ├── Stores all data as time series (90-day retention)      │
│  │  └── Responds to PromQL queries from Grafana                │
│  │                                                             │
│  │  Grafana (port 3000)                                        │
│  │  ├── Loads dashboard template from k6_results.json          │
│  │  ├── Queries Prometheus for each panel (PromQL)             │
│  │  └── Renders charts, graphs, gauges, stat panels            │
│  │                                                             │
│  └─────────────────────────────────────────────────────────────┘
```
