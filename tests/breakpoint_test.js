import { sleep } from "k6";
import { trafficMix, bookingSuccess, bookingFail, bookingSoldOut } from "./realistic_test.js";

/**
 * BREAKPOINT / CAPACITY TEST (Phase B)
 * Purpose: Find the absolute maximum throughput the system can handle.
 * Ramps arrival rate (RPS) continuously until the system collapses.
 *
 * Uses ramping-arrival-rate executor — controls RPS directly, not VU count.
 * K6 automatically allocates VUs as needed (up to maxVUs).
 *
 * Duration: ~20 minutes.
 *
 * What to look for:
 * - Max RPS before error rate exceeds 10%
 * - Max RPS before p99 exceeds 5s
 * - How many VUs K6 needed at peak (shown in output)
 */

export { bookingSuccess, bookingFail, bookingSoldOut };

export const options = {
  scenarios: {
    breakpoint: {
      executor: "ramping-arrival-rate",
      startRate: 10,
      timeUnit: "1s",
      preAllocatedVUs: 50,
      maxVUs: 500,
      stages: [
        { duration: "5m", target: 50 },    // warm up: 10→50 RPS
        { duration: "5m", target: 150 },   // push: 50→150 RPS
        { duration: "5m", target: 300 },   // heavy: 150→300 RPS
        { duration: "5m", target: 500 },   // extreme: 300→500 RPS
      ],
    },
  },
  // No hard thresholds — this test is observational.
  // We WANT to see where it breaks.
  thresholds: {
    http_req_duration: [{ threshold: "p(95)<5000", abortOnFail: true }],
  },
};

export default function () {
  trafficMix();
  // No sleep — arrival rate controls pacing
}
