/**
 * Midas Bank load test — exposes SQLite thread-safety bug under concurrent load.
 * 60 VUs at constant arrival rate → shared connection fails ~60% of requests.
 */
import http from "k6/http";
import { check, group, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

const transferLatency = new Trend("transfer_latency", true);
const accountLatency = new Trend("account_latency", true);
const validResponses = new Rate("valid_responses");

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const HEADERS = {
  "Authorization": "Bearer test-token-midas",
  "Content-Type": "application/json",
};

export const options = {
  scenarios: {
    warmup: {
      executor: "constant-arrival-rate",
      exec: "healthCheck",
      rate: 5, timeUnit: "1s", duration: "5s",
      preAllocatedVUs: 10, maxVUs: 20,
      startTime: "0s",
    },
    steady_load: {
      executor: "constant-arrival-rate",
      exec: "bankingFlow",
      rate: 15, timeUnit: "1s", duration: "20s",
      preAllocatedVUs: 40, maxVUs: 70,
      startTime: "5s",
      gracefulStop: "5s",
    },
    spike: {
      executor: "ramping-arrival-rate",
      exec: "bankingFlow",
      startRate: 15, timeUnit: "1s",
      stages: [{ target: 40, duration: "5s" }, { target: 10, duration: "5s" }],
      preAllocatedVUs: 50, maxVUs: 80,
      startTime: "25s",
      gracefulStop: "5s",
    },
  },
  thresholds: {
    "http_req_failed": ["rate<0.05"],
    "checks": ["rate>0.90"],
    "transfer_latency": ["p(95)<2000"],
    "account_latency": ["p(95)<500"],
  },
};

export function healthCheck() {
  const res = http.get(`${BASE_URL}/api/health`);
  check(res, { "health ok": (r) => r.status === 200 });
}

export function bankingFlow() {
  group("List Accounts", () => {
    const res = http.get(`${BASE_URL}/api/accounts`, { headers: HEADERS, tags: { endpoint: "list_accounts" } });
    accountLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has accounts array": (r) => Array.isArray(r.json()),
      "accounts non-empty": (r) => r.json().length > 0,
      "content-type json": (r) => r.headers["Content-Type"] && r.headers["Content-Type"].includes("application/json"),
    });
    validResponses.add(ok);
  });

  group("Get Account", () => {
    const res = http.get(`${BASE_URL}/api/accounts/1`, { headers: HEADERS, tags: { endpoint: "get_account" } });
    accountLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has id": (r) => r.json("id") === 1,
      "has balance": (r) => typeof r.json("balance") === "number",
      "balance non-negative": (r) => r.json("balance") >= 0,
      "has owner": (r) => typeof r.json("owner") === "string",
    });
    validResponses.add(ok);
  });

  group("Transfer", () => {
    const payload = JSON.stringify({ from_account_id: 1, to_account_id: 2, amount: 1.0, description: "load test" });
    const res = http.post(`${BASE_URL}/api/transactions/transfer`, payload, { headers: HEADERS, tags: { endpoint: "transfer" } });
    transferLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 201": (r) => r.status === 201,
      "has transaction id": (r) => r.status === 201 && typeof r.json("id") === "number",
      "correct amount": (r) => r.status === 201 && r.json("amount") === 1.0,
      "type is transfer": (r) => r.status === 201 && r.json("type") === "transfer",
    });
    validResponses.add(ok);
  });

  group("Get Balance", () => {
    const res = http.get(`${BASE_URL}/api/accounts/2/balance`, { headers: HEADERS, tags: { endpoint: "balance" } });
    accountLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has balance field": (r) => typeof r.json("balance") === "number",
    });
    validResponses.add(ok);
  });
}

export function handleSummary(data) {
  const slug = __ENV.REPORT_NAME || "midas-bank-test";
  return {
    [`k6/prometheus/results/${slug}.json`]: JSON.stringify(data, null, 2),
    stdout: JSON.stringify({ status: "complete", metrics: Object.keys(data.metrics).length }),
  };
}
