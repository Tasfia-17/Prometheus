# Midas Bank — BOB-CONFIG.md

## App Info

- **Stack:** Python / FastAPI / SQLite
- **Port:** 8000
- **Base URL:** http://localhost:8000
- **Health:** GET /api/health
- **Auth:** `Authorization: Bearer test-token-midas`

## SLOs

| Endpoint | p95 target |
|---|---|
| GET /api/accounts | 300ms |
| GET /api/accounts/{id} | 200ms |
| POST /api/transactions/transfer | 1500ms |
| POST /api/transactions/deposit | 1000ms |
| GET /api/accounts/{id}/balance | 200ms |

## Execution Command

```bash
./scripts/run-prometheus-test.sh k6/midas-bank-test.js midas
```

## Known Performance Fault

**SQLite thread-safety bug** — `app.py` line 18: a single `sqlite3.Connection` is created at module load and shared across all threads. FastAPI uses a thread pool for sync endpoints. Under concurrent load (60+ VUs), multiple threads share the same connection → `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`. Expect ~60% failure rate at 60 VUs.

**Fix:** Create a new connection per request using `threading.local()` or use SQLAlchemy with a connection pool.
