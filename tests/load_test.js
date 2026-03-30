import { sleep } from "k6";
import { trafficMix, bookingSuccess, bookingFail, bookingSoldOut } from "./realistic_test.js";
import { checkApiHealth, saveSummary, configureExpectedStatuses, randomSleep } from "./helpers.js";

configureExpectedStatuses(200, 404, 409);

/**
 * LOAD TEST (Phase B)
 * Purpose: Simulate expected normal + peak load.
 * Validates that the system meets performance SLAs under typical traffic.
 *
 * Profile: Ramp up to 50 VUs → hold for 5 min → ramp down.
 * Duration: ~8 minutes total.
 */

export { bookingSuccess, bookingFail, bookingSoldOut };

export const options = {
  stages: [
    { duration: "2m", target: 50 },   // ramp up to 50 VUs
    { duration: "5m", target: 50 },   // hold at 50 VUs (steady state)
    { duration: "1m", target: 0 },    // ramp down
  ],
  gracefulStop: "30s",
  tags: { testid: "load" },
  thresholds: {
    http_req_duration: ["p(95)<500", "p(99)<1000"],
    http_req_failed: ["rate<0.01"],
    checks: ["rate>0.95"],
  },
};

export function setup() { checkApiHealth(); }
export function handleSummary(data) { return saveSummary(data, "load_test"); }

export default function () {
  trafficMix();
  sleep(randomSleep(0.5, 2.0));
}
