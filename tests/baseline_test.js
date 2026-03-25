import http from "k6/http";
import { sleep, check } from "k6";
import { BASE_URL, randomUserId, randomEventId, randomBookingId, randomLocation } from "./helpers.js";

/**
 * BASELINE / SMOKE TEST
 * Purpose: Verify all endpoints are functional before running heavy tests.
 * Light load: 10 VUs, 30s. Every endpoint hit once per iteration.
 * If this test fails, do not proceed with other tests.
 */

export const options = {
  vus: 10,
  duration: "30s",
  thresholds: {
    http_req_duration: ["p(95)<300"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  // --- Health ---
  let health = http.get(`${BASE_URL}/health`, { tags: { name: "GetHealth" } });
  check(health, {
    "health status 200": (r) => r.status === 200,
    "health body ok": (r) => r.json().status === "ok",
  });

  // --- Users ---
  let users = http.get(`${BASE_URL}/users/?limit=5`, { tags: { name: "GetUsers" } });
  check(users, {
    "users status 200": (r) => r.status === 200,
    "users is array": (r) => Array.isArray(r.json()),
  });

  let userId = randomUserId();
  let user = http.get(`${BASE_URL}/users/${userId}`, { tags: { name: "GetUser" } });
  check(user, {
    "user status 200": (r) => r.status === 200,
  });

  let userBookings = http.get(`${BASE_URL}/users/${userId}/bookings?limit=5`, { tags: { name: "GetUserBookings" } });
  check(userBookings, {
    "user bookings status 200": (r) => r.status === 200,
  });

  // --- Events ---
  let events = http.get(`${BASE_URL}/events/?limit=5`, { tags: { name: "GetEvents" } });
  check(events, {
    "events status 200": (r) => r.status === 200,
    "events is array": (r) => Array.isArray(r.json()),
  });

  let eventId = randomEventId();
  let event = http.get(`${BASE_URL}/events/${eventId}`, { tags: { name: "GetEvent" } });
  check(event, {
    "event status 200": (r) => r.status === 200,
  });

  let upcoming = http.get(`${BASE_URL}/events/upcoming?limit=5`, { tags: { name: "GetUpcoming" } });
  check(upcoming, {
    "upcoming status 200": (r) => r.status === 200,
  });

  let loc = randomLocation();
  let search = http.get(`${BASE_URL}/events/search?location=${encodeURIComponent(loc)}&limit=5`, { tags: { name: "SearchEvents" } });
  check(search, {
    "search status 200": (r) => r.status === 200,
  });

  let popular = http.get(`${BASE_URL}/events/popular?limit=5`, { tags: { name: "GetPopular" } });
  check(popular, {
    "popular status 200": (r) => r.status === 200,
  });

  let stats = http.get(`${BASE_URL}/events/${eventId}/stats`, { tags: { name: "GetEventStats" } });
  check(stats, {
    "event stats status 200": (r) => r.status === 200,
  });

  let eventBookings = http.get(`${BASE_URL}/events/${eventId}/bookings?limit=5`, { tags: { name: "GetEventBookings" } });
  check(eventBookings, {
    "event bookings status 200": (r) => r.status === 200,
  });

  // --- Bookings ---
  let bookings = http.get(`${BASE_URL}/bookings/?limit=5`, { tags: { name: "GetBookings" } });
  check(bookings, {
    "bookings status 200": (r) => r.status === 200,
    "bookings is array": (r) => Array.isArray(r.json()),
  });

  let bookingId = randomBookingId();
  let booking = http.get(`${BASE_URL}/bookings/${bookingId}`, { tags: { name: "GetBooking" } });
  check(booking, {
    "booking status 200 or 404": (r) => r.status === 200 || r.status === 404,
  });

  // --- Global Stats ---
  let globalStats = http.get(`${BASE_URL}/stats`, { tags: { name: "GetGlobalStats" } });
  check(globalStats, {
    "global stats status 200": (r) => r.status === 200,
    "global stats has fields": (r) => r.json().total_users !== undefined,
  });

  sleep(1);
}
