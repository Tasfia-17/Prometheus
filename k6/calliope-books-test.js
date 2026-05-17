/**
 * Calliope Books load test — exposes route ordering bug.
 * GET /api/books/search is shadowed by /:id → 100% failure on search.
 */
import http from "k6/http";
import { check, group } from "k6";
import { Trend, Rate } from "k6/metrics";

const searchLatency = new Trend("search_latency", true);
const bookLatency = new Trend("book_latency", true);
const validResponses = new Rate("valid_responses");

const BASE_URL = __ENV.BASE_URL || "http://localhost:3000";
const HEADERS = { "Authorization": "Bearer test-token-calliope" };

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
      exec: "bookFlow",
      rate: 15, timeUnit: "1s", duration: "20s",
      preAllocatedVUs: 40, maxVUs: 70,
      startTime: "5s",
      gracefulStop: "5s",
    },
  },
  thresholds: {
    "http_req_failed": ["rate<0.05"],
    "checks": ["rate>0.90"],
    "search_latency": ["p(95)<500"],
    "book_latency": ["p(95)<300"],
  },
};

export function healthCheck() {
  const res = http.get(`${BASE_URL}/api/health`);
  check(res, { "health ok": (r) => r.status === 200 });
}

export function bookFlow() {
  group("List Books", () => {
    const res = http.get(`${BASE_URL}/api/books`, { headers: HEADERS, tags: { endpoint: "list_books" } });
    bookLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has books array": (r) => Array.isArray(r.json("books")),
      "books non-empty": (r) => r.json("books") && r.json("books").length > 0,
    });
    validResponses.add(ok);
  });

  group("Search Books (BUG: route shadowed)", () => {
    const res = http.get(`${BASE_URL}/api/books/search?q=Gatsby`, { headers: HEADERS, tags: { endpoint: "search" } });
    searchLatency.add(res.timings.duration);
    // This SHOULD return 200 with books array, but route ordering bug returns 404
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has books array": (r) => r.status === 200 && Array.isArray(r.json("books")),
    });
    validResponses.add(ok);
  });

  group("Get Book by ID", () => {
    const res = http.get(`${BASE_URL}/api/books/1`, { headers: HEADERS, tags: { endpoint: "get_book" } });
    bookLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has title": (r) => typeof r.json("title") === "string",
      "has author": (r) => typeof r.json("author") === "string",
      "has price": (r) => typeof r.json("price") === "number",
    });
    validResponses.add(ok);
  });

  group("Get Reviews", () => {
    const res = http.get(`${BASE_URL}/api/books/1/reviews`, { headers: HEADERS, tags: { endpoint: "reviews" } });
    bookLatency.add(res.timings.duration);
    const ok = check(res, {
      "status 200": (r) => r.status === 200,
      "has reviews array": (r) => Array.isArray(r.json("reviews")),
    });
    validResponses.add(ok);
  });
}

export function handleSummary(data) {
  const slug = __ENV.REPORT_NAME || "calliope-books-test";
  return {
    [`k6/prometheus/results/${slug}.json`]: JSON.stringify(data, null, 2),
    stdout: JSON.stringify({ status: "complete", metrics: Object.keys(data.metrics).length }),
  };
}
