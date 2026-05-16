/**
 * Hestia Eats load test — exposes unbounded fetchAll on /api/orders/history.
 * Under concurrent load, copying 500+ orders per request causes latency spikes.
 */
import http from "k6/http";
import { check, group } from "k6";
import { Trend, Rate } from "k6/metrics";

const historyLatency = new Trend("history_latency", true);
const orderLatency = new Trend("order_latency", true);
const validResponses = new Rate("valid_responses");

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";
const HEADERS = {
  "Authorization": "Bearer test-token-hestia",
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
      exec: "orderFlow",
      rate: 15, timeUnit: "1s", duration: "20s",
      preAllocatedVUs: 40, maxVUs: 70,
      startTime: "5s",
      gracefulStop: "5s",
    },
    spike: {
      executor: "ramping-arrival-rate",
      exec: "historyFlow",
      startRate: 10, timeUnit: "1s",
      stages: [{ target: 30, duration: "5s" }, { target: 5, duration: "5s" }],
      preAllocatedVUs: 40, maxVUs: 60,
      startTime: "25s",
      gracefulStop: "5s",
    },
  },
  thresholds: {
    "http_req_failed": ["rate<0.05"],
    "checks": ["rate>0.90"],
    "history_latency": ["p(95)<1000"],
    "order_latency": ["p(95)<500"],
  },
};

export function healthCheck() {
  const res = http.get(`${BASE_URL}/api/health`);
  check(res, { "health ok": (r) => r.status === 200 });
}

export function orderFlow() {
  group("List Restaurants", () => {
    const res = http.get(`${BASE_URL}/api/restaurants`, { headers: HEADERS, tags: { endpoint: "restaurants" } });
    orderLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has restaurants": (r) => Array.isArray(r.json("restaurants")),
      "restaurants non-empty": (r) => r.json("restaurants") && r.json("restaurants").length > 0,
    });
    validResponses.add(ok);
  });

  group("Get Menu", () => {
    const res = http.get(`${BASE_URL}/api/restaurants/1/menu`, { headers: HEADERS, tags: { endpoint: "menu" } });
    orderLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has items": (r) => Array.isArray(r.json("items")),
    });
    validResponses.add(ok);
  });

  group("Create Order", () => {
    const payload = JSON.stringify({
      restaurant_id: 1,
      items: [{ menu_item_id: 1, quantity: 1, price: 12.99 }],
    });
    const res = http.post(`${BASE_URL}/api/orders`, payload, { headers: HEADERS, tags: { endpoint: "create_order" } });
    orderLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 201": (r) => r.status === 201,
      "has order id": (r) => r.status === 201 && typeof r.json("id") === "number",
      "has total": (r) => r.status === 201 && typeof r.json("total") === "number",
      "status is pending": (r) => r.status === 201 && r.json("status") === "pending",
    });
    validResponses.add(ok);
  });
}

export function historyFlow() {
  group("Order History (BUG: unbounded fetchAll)", () => {
    const res = http.get(`${BASE_URL}/api/orders/history`, { headers: HEADERS, tags: { endpoint: "history" } });
    historyLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has orders array": (r) => Array.isArray(r.json("orders")),
      "has total": (r) => typeof r.json("total") === "number",
    });
    validResponses.add(ok);
  });

  group("Order Stats", () => {
    const res = http.get(`${BASE_URL}/api/orders/history/stats`, { headers: HEADERS, tags: { endpoint: "stats" } });
    historyLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has total_orders": (r) => typeof r.json("total_orders") === "number",
      "has total_revenue": (r) => typeof r.json("total_revenue") === "number",
    });
    validResponses.add(ok);
  });
}

export function handleSummary(data) {
  return {
    "k6/prometheus/results/hestia-eats-test.json": JSON.stringify(data, null, 2),
    stdout: JSON.stringify({ status: "complete", metrics: Object.keys(data.metrics).length }),
  };
}
