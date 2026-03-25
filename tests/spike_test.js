import { sleep } from "k6";
import { trafficMix, bookingSuccess, bookingFail, bookingSoldOut } from "./realistic_test.js";

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
  thresholds: {
    http_req_duration: ["p(95)<2000"],  // generous — spikes cause queuing
    http_req_failed: ["rate<0.15"],     // some errors expected during spike
  },
};

export default function () {
  trafficMix();
  sleep(0.5);
}
