import http from "k6/http";
import { sleep, check } from "k6";
import { Counter } from "k6/metrics";
import { BASE_URL, JSON_HEADERS, randomUserId, randomEventId, randomBookingId, randomLocation, checkApiHealth, saveSummary, configureExpectedStatuses, randomSleep } from "./helpers.js";

configureExpectedStatuses(200, 404, 409);

/**
 * READ vs WRITE TEST (Phase C)
 * Purpose: Compare system behavior under read-heavy vs write-heavy traffic.
 * Two scenarios run sequentially:
 *   1. read_heavy: 90% reads / 10% writes
 *   2. write_heavy: 40% reads / 60% writes
 *
 * Shows how write locks (with_for_update) affect concurrent read performance.
 * Duration: ~7 minutes total (3 min each + 10s gap).
 */

const readHeavyBookings = new Counter("read_heavy_bookings");
const writeHeavyBookings = new Counter("write_heavy_bookings");

export const options = {
  scenarios: {
    read_heavy: {
      executor: "constant-vus",
      vus: 30,
      duration: "3m",
      gracefulStop: "30s",
      startTime: "0s",
      exec: "readHeavyProfile",
      tags: { scenario: "read_heavy", testid: "read_vs_write" },
    },
    write_heavy: {
      executor: "constant-vus",
      vus: 30,
      duration: "3m",
      gracefulStop: "30s",
      startTime: "190s",
      exec: "writeHeavyProfile",
      tags: { scenario: "write_heavy", testid: "read_vs_write" },
    },
  },
  thresholds: {
    "http_req_duration{scenario:read_heavy}": ["p(95)<500"],
    "http_req_duration{scenario:write_heavy}": ["p(95)<1500"],
    http_req_failed: ["rate<0.05"],
    checks: ["rate>0.95"],
  },
};

export function setup() { checkApiHealth(); }
export function handleSummary(data) { return saveSummary(data, "read_vs_write_test"); }

// --- Read-heavy: 90% reads, 10% writes ---
export function readHeavyProfile() {
  let r = Math.random();

  if (r < 0.30) {
    let res = http.get(`${BASE_URL}/events/?limit=20`, { tags: { name: "RH_BrowseEvents" } });
    check(res, { "200": (r) => r.status === 200 });
  } else if (r < 0.50) {
    let eventId = randomEventId();
    let res = http.get(`${BASE_URL}/events/${eventId}`, { tags: { name: "RH_ViewEvent" } });
    check(res, { "200": (r) => r.status === 200 });
  } else if (r < 0.65) {
    let loc = randomLocation();
    let res = http.get(`${BASE_URL}/events/search?location=${encodeURIComponent(loc)}&limit=20`, { tags: { name: "RH_Search" } });
    check(res, { "200": (r) => r.status === 200 });
  } else if (r < 0.80) {
    let res = http.get(`${BASE_URL}/users/?limit=20`, { tags: { name: "RH_ListUsers" } });
    check(res, { "200": (r) => r.status === 200 });
  } else if (r < 0.90) {
    let res = http.get(`${BASE_URL}/stats`, { tags: { name: "RH_GlobalStats" } });
    check(res, { "200": (r) => r.status === 200 });
  } else {
    // 10% writes
    let userId = randomUserId();
    let eventId = randomEventId();
    let payload = JSON.stringify({ user_id: userId, event_id: eventId });
    let res = http.post(`${BASE_URL}/bookings/`, payload, {
      ...JSON_HEADERS,
      tags: { name: "RH_CreateBooking" },
    });
    if (res.status === 200) readHeavyBookings.add(1);
    check(res, { "booking ok": (r) => r.status === 200 || r.status === 409 });
  }

  sleep(randomSleep(0.3, 1.0));
}

// --- Write-heavy: 40% reads, 60% writes ---
export function writeHeavyProfile() {
  let r = Math.random();

  if (r < 0.20) {
    let res = http.get(`${BASE_URL}/events/?limit=20`, { tags: { name: "WH_BrowseEvents" } });
    check(res, { "200": (r) => r.status === 200 });
  } else if (r < 0.40) {
    let eventId = randomEventId();
    let res = http.get(`${BASE_URL}/events/${eventId}`, { tags: { name: "WH_ViewEvent" } });
    check(res, { "200": (r) => r.status === 200 });
  } else if (r < 0.75) {
    // 35% create booking
    let userId = randomUserId();
    let eventId = randomEventId();
    let payload = JSON.stringify({ user_id: userId, event_id: eventId });
    let res = http.post(`${BASE_URL}/bookings/`, payload, {
      ...JSON_HEADERS,
      tags: { name: "WH_CreateBooking" },
    });
    if (res.status === 200) writeHeavyBookings.add(1);
    check(res, { "booking ok": (r) => r.status === 200 || r.status === 409 });
  } else {
    // 25% cancel booking
    let bookingId = randomBookingId();
    let res = http.patch(`${BASE_URL}/bookings/${bookingId}/cancel`, null, {
      tags: { name: "WH_CancelBooking" },
    });
    check(res, { "cancel ok": (r) => r.status === 200 || r.status === 409 || r.status === 404 });
  }

  sleep(randomSleep(0.3, 1.0));
}
