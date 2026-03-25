import http from "k6/http";
import { sleep, check } from "k6";
import { Counter, Trend } from "k6/metrics";
import { BASE_URL, JSON_HEADERS, randomUserId } from "./helpers.js";

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
const TARGET_EVENT_ID = 1;

export const options = {
  vus: 50,
  duration: "2m",
  thresholds: {
    contention_booking_latency: ["p(95)<3000"],
    http_req_failed: ["rate<0.05"],
  },
};

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

  sleep(0.5);
}
