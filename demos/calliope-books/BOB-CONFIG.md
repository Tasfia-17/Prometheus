# Calliope Books — BOB-CONFIG.md

## App Info

- **Stack:** Node.js / Express / sql.js
- **Port:** 3000
- **Base URL:** http://localhost:3000
- **Health:** GET /api/health
- **Auth:** `Authorization: Bearer test-token-calliope`

## SLOs

| Endpoint | p95 target |
|---|---|
| GET /api/books | 300ms |
| GET /api/books/search | 300ms |
| GET /api/books/{id} | 200ms |
| GET /api/books/{id}/reviews | 200ms |
| POST /api/books/{id}/reviews | 500ms |

## Execution Command

```bash
./scripts/run-prometheus-test.sh k6/calliope-books-test.js calliope
```

## Known Performance Fault

**Route ordering bug** — `app.js` line 63: `GET /api/books/:id` is registered BEFORE `GET /api/books/search`. Express matches routes in registration order, so the string "search" is treated as a book ID → 404 for every search request. Expect 100% failure rate on the search endpoint.

**Fix:** Move `app.get('/api/books/search', ...)` to BEFORE `app.get('/api/books/:id', ...)`.
