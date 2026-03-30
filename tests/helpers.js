import http from "k6/http";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.1/index.js";

export const BASE_URL = "http://localhost:8000";

// Per-test response callback configuration — call at module level in each test file.
export function configureExpectedStatuses(...statuses) {
  http.setResponseCallback(http.expectedStatuses(...statuses));
}

// Variable think time for realistic workload modeling.
export function randomSleep(min = 0.5, max = 2.0) {
  return min + Math.random() * (max - min);
}

export const JSON_HEADERS = {
  headers: { "Content-Type": "application/json" },
};

export const LOCATIONS = [
  "Zagreb", "Split", "Rijeka", "Osijek",
  "Zadar", "Varaždin", "Dubrovnik", "Pula",
];

export function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export function randomUserId() {
  return randomInt(1, 1000);
}

export function randomEventId() {
  return randomInt(1, 100);
}

export function randomBookingId() {
  return randomInt(1, 2000);
}

export function randomLocation() {
  return LOCATIONS[Math.floor(Math.random() * LOCATIONS.length)];
}

export function checkApiHealth() {
  let res = http.get(`${BASE_URL}/health`);
  if (res.status !== 200) {
    throw new Error(`API is not healthy (status ${res.status})! Run: docker compose restart api`);
  }
}

// Set WORKERS env var to label output files (default: "1w")
// Usage: k6 run -e WORKERS=4w tests/load_test.js
const WORKERS = __ENV.WORKERS || "1w";

export function saveSummary(data, testName) {
  return {
    stdout: textSummary(data, { indent: " ", enableColors: true }),
    [`results/${WORKERS}/${testName}.json`]: JSON.stringify(data, null, 2),
  };
}
