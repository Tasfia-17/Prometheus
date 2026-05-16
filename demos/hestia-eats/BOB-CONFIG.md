# Hestia Eats — BOB-CONFIG.md

## App Info

- **Stack:** Node.js / Hono / in-memory
- **Port:** 8080
- **Base URL:** http://localhost:8080
- **Health:** GET /api/health
- **Auth:** `Authorization: Bearer test-token-hestia`

## SLOs

| Endpoint | p95 target |
|---|---|
| GET /api/restaurants | 200ms |
| GET /api/restaurants/{id}/menu | 200ms |
| POST /api/orders | 500ms |
| GET /api/orders/history | 800ms |
| GET /api/orders/history/stats | 500ms |

## Execution Command

```bash
./scripts/run-prometheus-test.sh k6/hestia-eats-test.js hestia
```

## Known Performance Fault

**Unbounded fetchAll** — `app.js` line 89: `orders.slice()` copies the entire orders array (500+ items) into memory on every request to `/api/orders/history`. Under concurrent load, this causes latency spikes as memory pressure increases with each concurrent copy.

**Fix:** Add pagination — `orders.slice(offset, offset + limit)` with `limit` and `offset` query params.
