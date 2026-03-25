import http from "k6/http";
import { sleep, check } from "k6";
import { BASE_URL, JSON_HEADERS, randomUserId, randomEventId, randomBookingId, randomLocation } from "./helpers.js";

/**
 * ENDPOINT BENCHMARK TEST (Phase A)
 * Purpose: Isolate each endpoint category under controlled load.
 * Each scenario runs sequentially (via startTime offset) so they don't interfere.
 * Produces per-scenario metrics for the thesis comparison table.
 */

const SCENARIO_DURATION = "1m";
const SCENARIO_VUS = 20;

export const options = {
  scenarios: {
    light_reads: {
      executor: "constant-vus",
      vus: SCENARIO_VUS,
      duration: SCENARIO_DURATION,
      startTime: "0s",
      exec: "lightReads",
      tags: { scenario: "light_reads" },
    },
    list_reads: {
      executor: "constant-vus",
      vus: SCENARIO_VUS,
      duration: SCENARIO_DURATION,
      startTime: "70s",
      exec: "listReads",
      tags: { scenario: "list_reads" },
    },
    search_filter: {
      executor: "constant-vus",
      vus: SCENARIO_VUS,
      duration: SCENARIO_DURATION,
      startTime: "140s",
      exec: "searchFilter",
      tags: { scenario: "search_filter" },
    },
    writes: {
      executor: "constant-vus",
      vus: SCENARIO_VUS,
      duration: SCENARIO_DURATION,
      startTime: "210s",
      exec: "writes",
      tags: { scenario: "writes" },
    },
    heavy_aggregations: {
      executor: "constant-vus",
      vus: SCENARIO_VUS,
      duration: SCENARIO_DURATION,
      startTime: "280s",
      exec: "heavyAggregations",
      tags: { scenario: "heavy_aggregations" },
    },
  },
  thresholds: {
    "http_req_duration{scenario:light_reads}": ["p(95)<200"],
    "http_req_duration{scenario:list_reads}": ["p(95)<500"],
    "http_req_duration{scenario:search_filter}": ["p(95)<500"],
    "http_req_duration{scenario:writes}": ["p(95)<1000"],
    "http_req_duration{scenario:heavy_aggregations}": ["p(95)<1500"],
    http_req_failed: ["rate<0.05"],
  },
};

// --- Scenario: Light Reads (PK lookups) ---
export function lightReads() {
  let healthRes = http.get(`${BASE_URL}/health`, { tags: { name: "GetHealth" } });
  check(healthRes, { "health 200": (r) => r.status === 200 });

  let userId = randomUserId();
  let userRes = http.get(`${BASE_URL}/users/${userId}`, { tags: { name: "GetUser" } });
  check(userRes, { "user 200": (r) => r.status === 200 });

  let eventId = randomEventId();
  let eventRes = http.get(`${BASE_URL}/events/${eventId}`, { tags: { name: "GetEvent" } });
  check(eventRes, { "event 200": (r) => r.status === 200 });

  let bookingId = randomBookingId();
  let bookingRes = http.get(`${BASE_URL}/bookings/${bookingId}`, { tags: { name: "GetBooking" } });
  check(bookingRes, { "booking 200 or 404": (r) => r.status === 200 || r.status === 404 });

  sleep(0.5);
}

// --- Scenario: List Reads (paginated queries) ---
export function listReads() {
  let usersRes = http.get(`${BASE_URL}/users/?limit=100`, { tags: { name: "ListUsers" } });
  check(usersRes, { "users 200": (r) => r.status === 200 });

  let eventsRes = http.get(`${BASE_URL}/events/?limit=100`, { tags: { name: "ListEvents" } });
  check(eventsRes, { "events 200": (r) => r.status === 200 });

  let bookingsRes = http.get(`${BASE_URL}/bookings/?limit=100`, { tags: { name: "ListBookings" } });
  check(bookingsRes, { "bookings 200": (r) => r.status === 200 });

  sleep(0.5);
}

// --- Scenario: Search & Filter ---
export function searchFilter() {
  let loc = randomLocation();
  let searchRes = http.get(`${BASE_URL}/events/search?location=${encodeURIComponent(loc)}&limit=50`, { tags: { name: "SearchEvents" } });
  check(searchRes, { "search 200": (r) => r.status === 200 });

  let upcomingRes = http.get(`${BASE_URL}/events/upcoming?limit=50`, { tags: { name: "UpcomingEvents" } });
  check(upcomingRes, { "upcoming 200": (r) => r.status === 200 });

  let userId = randomUserId();
  let userBookingsRes = http.get(`${BASE_URL}/users/${userId}/bookings?limit=50`, { tags: { name: "UserBookings" } });
  check(userBookingsRes, { "user bookings 200": (r) => r.status === 200 });

  let eventId = randomEventId();
  let eventBookingsRes = http.get(`${BASE_URL}/events/${eventId}/bookings?limit=50`, { tags: { name: "EventBookings" } });
  check(eventBookingsRes, { "event bookings 200": (r) => r.status === 200 });

  sleep(0.5);
}

// --- Scenario: Writes (booking create + cancel) ---
export function writes() {
  let userId = randomUserId();
  let eventId = randomEventId();

  let payload = JSON.stringify({ user_id: userId, event_id: eventId });
  let createRes = http.post(`${BASE_URL}/bookings/`, payload, {
    ...JSON_HEADERS,
    tags: { name: "CreateBooking" },
  });
  check(createRes, {
    "booking created or sold out": (r) => r.status === 200 || r.status === 409,
  });

  // Cancel a random existing booking
  let bookingId = randomBookingId();
  let cancelRes = http.patch(`${BASE_URL}/bookings/${bookingId}/cancel`, null, {
    tags: { name: "CancelBooking" },
  });
  check(cancelRes, {
    "cancel ok or already cancelled or not found": (r) =>
      r.status === 200 || r.status === 409 || r.status === 404,
  });

  sleep(0.5);
}

// --- Scenario: Heavy Aggregations (JOINs, GROUP BY, subqueries) ---
export function heavyAggregations() {
  let eventId = randomEventId();
  let statsRes = http.get(`${BASE_URL}/events/${eventId}/stats`, { tags: { name: "EventStats" } });
  check(statsRes, { "event stats 200": (r) => r.status === 200 });

  let popularRes = http.get(`${BASE_URL}/events/popular?limit=10`, { tags: { name: "PopularEvents" } });
  check(popularRes, { "popular 200": (r) => r.status === 200 });

  let globalRes = http.get(`${BASE_URL}/stats`, { tags: { name: "GlobalStats" } });
  check(globalRes, { "global stats 200": (r) => r.status === 200 });

  sleep(0.5);
}
