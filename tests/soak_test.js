import { sleep } from "k6";
import { trafficMix, bookingSuccess, bookingFail, bookingSoldOut } from "./realistic_test.js";
import { checkApiHealth, saveSummary } from "./helpers.js";

/**
 * SOAK TEST (Phase B)
 * Purpose: Detect memory leaks, connection pool exhaustion, and DB bloat.
 * Run moderate load for an extended period and watch for latency drift.
 *
 * Profile: 30 VUs held for 30 minutes.
 * Duration: ~32 minutes total.
 *
 * What to look for:
 * - Latency increasing over time = memory leak or connection exhaustion
 * - Error rate climbing = resource exhaustion
 * - Flat latency = system is stable
 */

export { bookingSuccess, bookingFail, bookingSoldOut };

export const options = {
  stages: [
    { duration: "1m", target: 30 },    // ramp up
    { duration: "30m", target: 30 },   // sustained load
    { duration: "1m", target: 0 },     // ramp down
  ],
  tags: { testid: "soak" },
  thresholds: {
    http_req_duration: ["p(95)<700"],
    http_req_failed: ["rate<0.01"],
  },
};

export function setup() { checkApiHealth(); }
export function handleSummary(data) { return saveSummary(data, "soak_test"); }

export default function () {
  trafficMix();
  sleep(1);
}
