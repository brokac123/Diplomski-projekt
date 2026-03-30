import http from "k6/http";
import { sleep, check } from "k6";
import { Counter, Trend } from "k6/metrics";
import { BASE_URL, JSON_HEADERS, randomUserId, checkApiHealth, saveSummary, configureExpectedStatuses, randomSleep } from "./helpers.js";

configureExpectedStatuses(200, 409);

/**
 * CONTENTION TEST (Phase C)
 * Purpose: Test row-level locking (with_for_update) under high contention.
 * All VUs target the SAME event — forces PostgreSQL row lock contention.
 *
 * This test answers:
 * - How does with_for_update() behave when 50 users book the same event?
 * - What latency does lock waiting add?
 * - How fast do tickets sell out?
 * - Are there any deadlocks or errors?
 *
 * Duration: 2 minutes.
 */

const contentionBookingSuccess = new Counter("contention_booking_success");
const contentionBookingSoldOut = new Counter("contention_booking_sold_out");
const contentionBookingLatency = new Trend("contention_booking_latency");

// All VUs target the same event to maximize lock contention
const TARGET_EVENT_ID = parseInt(__ENV.TARGET_EVENT_ID || "1", 10);

export const options = {
  vus: 50,
  duration: "2m",
  gracefulStop: "30s",
  tags: { testid: "contention" },
  thresholds: {
    contention_booking_latency: ["p(95)<3000"],
    http_req_failed: ["rate<0.05"],
    checks: ["rate>0.95"],
  },
};

export function setup() {
  checkApiHealth();

  let res = http.get(`${BASE_URL}/events/${TARGET_EVENT_ID}`, { tags: { name: "SetupCheck" } });
  if (res.status !== 200) {
    throw new Error(`Target event ${TARGET_EVENT_ID} not found (status ${res.status}). Re-seed database or set TARGET_EVENT_ID env var.`);
  }

  let event = res.json();
  if (event.available_tickets <= 0) {
    console.warn(`WARNING: Event ${TARGET_EVENT_ID} has 0 available tickets. Re-seed: docker compose exec api python seed_data.py --reset`);
  }

  return { targetEventId: TARGET_EVENT_ID, initialTickets: event.available_tickets };
}
export function handleSummary(data) { return saveSummary(data, "contention_test"); }

export default function () {
  let userId = randomUserId();
  let payload = JSON.stringify({ user_id: userId, event_id: TARGET_EVENT_ID });

  let res = http.post(`${BASE_URL}/bookings/`, payload, {
    ...JSON_HEADERS,
    tags: { name: "ContentionBooking" },
  });

  contentionBookingLatency.add(res.timings.duration);

  if (res.status === 200) {
    contentionBookingSuccess.add(1);
  } else if (res.status === 409) {
    contentionBookingSoldOut.add(1);
  }

  check(res, {
    "booking or sold out": (r) => r.status === 200 || r.status === 409,
  });

  // Also read the event to see lock contention effect on reads
  let eventRes = http.get(`${BASE_URL}/events/${TARGET_EVENT_ID}`, {
    tags: { name: "ContentionEventRead" },
  });
  check(eventRes, { "event read 200": (r) => r.status === 200 });

  sleep(randomSleep(0.3, 1.0));
}
