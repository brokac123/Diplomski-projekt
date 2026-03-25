import http from "k6/http";
import { sleep, check } from "k6";
import { Counter } from "k6/metrics";
import { BASE_URL, JSON_HEADERS, randomUserId, randomEventId, randomBookingId, randomLocation } from "./helpers.js";

/**
 * REALISTIC TRAFFIC TEST
 * Purpose: Simulate realistic mixed traffic with proper distribution.
 * Also serves as standalone test: 20 VUs, 1 min.
 *
 * Traffic distribution (mirrors real-world booking platform usage):
 *  25% — Browse events list
 *  15% — View single event
 *  10% — Search events by location
 *   8% — Upcoming events
 *  10% — List users
 *   5% — View user bookings
 *  12% — Create booking (write)
 *   5% — Cancel booking (write)
 *   5% — Event stats (heavy)
 *   3% — Popular events (heavy)
 *   2% — Global stats (heavy)
 */

// --- Custom Metrics ---
export const bookingSuccess = new Counter("booking_success");
export const bookingFail = new Counter("booking_fail");
export const bookingSoldOut = new Counter("booking_sold_out");

export const options = {
  vus: 20,
  duration: "1m",
  thresholds: {
    http_req_duration: ["p(95)<500", "p(99)<1000"],
    http_req_failed: ["rate<0.01"],
  },
};

/**
 * Exported traffic function — reused by load, stress, spike, soak tests.
 * Each call simulates one "user action" based on weighted random selection.
 */
export function trafficMix() {
  let r = Math.random();

  if (r < 0.25) {
    // 25% — Browse events
    let res = http.get(`${BASE_URL}/events/?limit=20`, { tags: { name: "BrowseEvents" } });
    check(res, { "events 200": (r) => r.status === 200 });

  } else if (r < 0.40) {
    // 15% — View single event
    let eventId = randomEventId();
    let res = http.get(`${BASE_URL}/events/${eventId}`, { tags: { name: "ViewEvent" } });
    check(res, { "event 200": (r) => r.status === 200 });

  } else if (r < 0.50) {
    // 10% — Search events
    let loc = randomLocation();
    let res = http.get(`${BASE_URL}/events/search?location=${encodeURIComponent(loc)}&limit=20`, { tags: { name: "SearchEvents" } });
    check(res, { "search 200": (r) => r.status === 200 });

  } else if (r < 0.58) {
    // 8% — Upcoming events
    let res = http.get(`${BASE_URL}/events/upcoming?limit=20`, { tags: { name: "UpcomingEvents" } });
    check(res, { "upcoming 200": (r) => r.status === 200 });

  } else if (r < 0.68) {
    // 10% — List users
    let res = http.get(`${BASE_URL}/users/?limit=20`, { tags: { name: "ListUsers" } });
    check(res, { "users 200": (r) => r.status === 200 });

  } else if (r < 0.73) {
    // 5% — User bookings
    let userId = randomUserId();
    let res = http.get(`${BASE_URL}/users/${userId}/bookings?limit=20`, { tags: { name: "UserBookings" } });
    check(res, { "user bookings 200": (r) => r.status === 200 });

  } else if (r < 0.85) {
    // 12% — Create booking
    let userId = randomUserId();
    let eventId = randomEventId();
    let payload = JSON.stringify({ user_id: userId, event_id: eventId });
    let res = http.post(`${BASE_URL}/bookings/`, payload, {
      ...JSON_HEADERS,
      tags: { name: "CreateBooking" },
    });

    if (res.status === 200) {
      bookingSuccess.add(1);
    } else if (res.status === 409) {
      bookingSoldOut.add(1);
    } else {
      bookingFail.add(1);
    }
    check(res, {
      "booking created or sold out": (r) => r.status === 200 || r.status === 409,
    });

  } else if (r < 0.90) {
    // 5% — Cancel booking
    let bookingId = randomBookingId();
    let res = http.patch(`${BASE_URL}/bookings/${bookingId}/cancel`, null, {
      tags: { name: "CancelBooking" },
    });
    check(res, {
      "cancel ok or expected error": (r) => r.status === 200 || r.status === 409 || r.status === 404,
    });

  } else if (r < 0.95) {
    // 5% — Event stats
    let eventId = randomEventId();
    let res = http.get(`${BASE_URL}/events/${eventId}/stats`, { tags: { name: "EventStats" } });
    check(res, { "event stats 200": (r) => r.status === 200 });

  } else if (r < 0.98) {
    // 3% — Popular events
    let res = http.get(`${BASE_URL}/events/popular?limit=10`, { tags: { name: "PopularEvents" } });
    check(res, { "popular 200": (r) => r.status === 200 });

  } else {
    // 2% — Global stats
    let res = http.get(`${BASE_URL}/stats`, { tags: { name: "GlobalStats" } });
    check(res, { "global stats 200": (r) => r.status === 200 });
  }
}

// Default function for standalone execution
export default function () {
  trafficMix();
  sleep(1);
}
