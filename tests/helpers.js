import http from "k6/http";

// Tell K6 that 404 and 409 are expected business responses, not errors.
// Without this, http_req_failed counts sold-out (409) and not-found (404) as failures.
http.setResponseCallback(http.expectedStatuses(200, 404, 409));

export const BASE_URL = "http://localhost:8000";

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
