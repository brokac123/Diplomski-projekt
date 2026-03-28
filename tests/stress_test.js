import { sleep } from "k6";
import { trafficMix, bookingSuccess, bookingFail, bookingSoldOut } from "./realistic_test.js";
import { checkApiHealth, saveSummary } from "./helpers.js";

/**
 * STRESS TEST (Phase B)
 * Purpose: Progressively increase load beyond normal capacity.
 * Find the degradation point — at what VU count does p99 spike or errors appear?
 *
 * Profile: Step up from 50 → 100 → 200 → 300 VUs.
 * Duration: ~8 minutes total.
 */

export { bookingSuccess, bookingFail, bookingSoldOut };

export const options = {
  stages: [
    { duration: "1m", target: 50 },    // warm up
    { duration: "2m", target: 100 },   // normal load
    { duration: "2m", target: 200 },   // above normal
    { duration: "2m", target: 300 },   // stress level
    { duration: "1m", target: 0 },     // ramp down
  ],
  tags: { testid: "stress" },
  thresholds: {
    http_req_duration: ["p(95)<1500"],  // relaxed — we expect degradation
    http_req_failed: ["rate<0.10"],     // up to 10% errors acceptable at peak
  },
};

export function setup() { checkApiHealth(); }
export function handleSummary(data) { return saveSummary(data, "stress_test"); }

export default function () {
  trafficMix();
  sleep(0.5);
}
