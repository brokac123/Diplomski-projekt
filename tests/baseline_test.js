import http from "k6/http";
import { sleep, check } from "k6";

export const options = {
  vus: 20,           // virtual users
  duration: "30s",   // trajanje testa
};

const BASE_URL = "http://localhost:8000";

export default function () {

  // GET events
  let events = http.get(`${BASE_URL}/events/`);
  check(events, {
    "events status 200": (r) => r.status === 200,
  });

  // GET users
  let users = http.get(`${BASE_URL}/users/`);
  check(users, {
    "users status 200": (r) => r.status === 200,
  });

  // GET bookings
  let bookings = http.get(`${BASE_URL}/bookings/`);
  check(bookings, {
    "bookings status 200": (r) => r.status === 200,
  });

  sleep(1);
}