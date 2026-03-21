import http from "k6/http";
import { sleep, check } from "k6";

export const options = {
  vus: 15,
  duration: "30s",
};

const BASE_URL = "http://localhost:8000";

export default function () {

  let random = Math.random();

  // 50% users list events
  if (random < 0.5) {
    let res = http.get(`${BASE_URL}/events/`);
    check(res, { "events ok": (r) => r.status === 200 });
  }

  // 20% users list users
  else if (random < 0.7) {
    let res = http.get(`${BASE_URL}/users/`);
    check(res, { "users ok": (r) => r.status === 200 });
  }

  // 15% get single event
  else if (random < 0.85) {
    let id = Math.floor(Math.random() * 101) + 1;
    let res = http.get(`${BASE_URL}/events/${id}`);
    check(res, { "event detail ok": (r) => r.status === 200 });
  }

  // 15% booking attempt
  else {

    let user_id = Math.floor(Math.random() * 1000) + 1;
    let event_id = Math.floor(Math.random() * 100) + 1;

    let payload = JSON.stringify({
      user_id: user_id,
      event_id: event_id
    });

    let params = {
      headers: {
        "Content-Type": "application/json"
      }
    };

    let res = http.post(`${BASE_URL}/bookings/`, payload, params);

    check(res, {
      "booking response": (r) => r.status === 200 || r.status === 400
    });
  }

  sleep(1);
}