import { sleep } from "k6";
import { trafficMix, bookingSuccess, bookingFail, bookingSoldOut } from "./realistic_test.js";
import { checkApiHealth, saveSummary, configureExpectedStatuses } from "./helpers.js";

configureExpectedStatuses(200, 404, 409);

/**
 * RECOVERY TEST (Phase C)
 * Purpose: Measure how long the system takes to recover after sudden overload.
 * Unlike the spike test (which focuses on behavior during the spike), this test
 * has a long post-spike observation window to measure time-to-recovery.
 *
 * Key thesis metric: How many seconds after the spike ends does p95 return
 * to baseline levels? Compare 1w vs 2w vs 4w recovery times.
 *
 * Profile:
 *   1 min baseline (30 VUs) → establish normal p95
 *   10s spike to 300 VUs → overload
 *   30s hold at 300 VUs → sustained overload
 *   10s drop to 30 VUs → spike ends
 *   4 min observation (30 VUs) → measure recovery
 *
 * Duration: ~6 minutes total.
 *
 * What to look for in Grafana:
 * - p95 during baseline (first minute) = the "normal" reference
 * - p95 during the 4-min observation window = the recovery curve
 * - The timestamp where p95 returns to baseline = recovery time
 * - If p95 never returns to baseline = no recovery (1-worker expected behavior)
 */

export { bookingSuccess, bookingFail, bookingSoldOut };

export const options = {
  stages: [
    { duration: "1m", target: 30 },    // baseline — establish normal p95
    { duration: "10s", target: 300 },   // spike UP
    { duration: "30s", target: 300 },   // hold spike
    { duration: "10s", target: 30 },    // spike DOWN
    { duration: "4m", target: 30 },     // recovery observation (long window)
    { duration: "20s", target: 0 },     // ramp down
  ],
  gracefulStop: "30s",
  tags: { testid: "recovery" },
  thresholds: {
    // Intentionally generous — we WANT to observe recovery, not pass/fail
    http_req_duration: ["p(95)<10000"],
    http_req_failed: ["rate<0.30"],
    checks: ["rate>0.70"],
  },
};

export function setup() { checkApiHealth(); }
export function handleSummary(data) { return saveSummary(data, "recovery_test"); }

export default function () {
  trafficMix();
  sleep(0.5);
}
