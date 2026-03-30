import { sleep } from "k6";
import { trafficMix, bookingSuccess, bookingFail, bookingSoldOut } from "./realistic_test.js";
import { checkApiHealth, saveSummary, configureExpectedStatuses } from "./helpers.js";

configureExpectedStatuses(200, 404, 409);

/**
 * SPIKE TEST (Phase B)
 * Purpose: Test system behavior under sudden traffic burst.
 * Key question: Does the API recover after the spike, or do errors persist?
 *
 * Profile: Low baseline → sudden spike to 300 VUs → drop back to baseline.
 * Duration: ~3.5 minutes total.
 */

export { bookingSuccess, bookingFail, bookingSoldOut };

export const options = {
  stages: [
    { duration: "30s", target: 10 },   // baseline
    { duration: "1m", target: 10 },    // hold baseline
    { duration: "10s", target: 300 },  // SPIKE UP
    { duration: "30s", target: 300 },  // hold spike
    { duration: "10s", target: 10 },   // SPIKE DOWN
    { duration: "1m", target: 10 },    // recovery period
    { duration: "10s", target: 0 },    // ramp down
  ],
  gracefulStop: "30s",
  tags: { testid: "spike" },
  thresholds: {
    http_req_duration: ["p(95)<2000"],  // generous — spikes cause queuing
    http_req_failed: ["rate<0.15"],     // some errors expected during spike
    checks: ["rate>0.85"],
  },
};

export function setup() { checkApiHealth(); }
export function handleSummary(data) { return saveSummary(data, "spike_test"); }

export default function () {
  trafficMix();
  sleep(0.5);
}
