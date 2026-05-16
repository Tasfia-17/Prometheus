# Prometheus: AI Performance Testing Agent

> Performance prophecy for every pull request — powered by IBM Bob.

Prometheus turns IBM Bob's full repository context into executable k6 load tests. Point Bob at any repo, ask it to performance-test a branch, and it reads the diff, understands the full call chain, generates a k6 script, runs it, and posts a structured report with real latency numbers, threshold verdicts, and root cause analysis.

**The loop:** Bob reads repo → GraphRAG extracts schemas → Bob generates k6 script → shell runs k6 → Python generates report → Bob interprets results with full codebase context.

## Why This Exists

Performance bugs are invisible in serial testing. A FastAPI endpoint that passes 100% of unit tests can fail 60% of requests under concurrent load due to SQLite thread-safety. An Express route ordering bug produces 100% failure only when multiple users hit it simultaneously. Unit tests verify logic. Load tests verify behavior under production conditions.

No existing tool closes the full loop: read a diff → generate a targeted load test → run it → post results. **IBM Bob's full repository context is the key differentiator** — when k6 reports 60% failure rate, Bob traces the failure to `db.py`, the connection pool setup, the middleware stack. Root cause analysis grounded in the full codebase, not just the changed lines.

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) installed

### Run a test

```bash
# Midas Bank (SQLite thread-safety bug)
./scripts/run-prometheus-test.sh k6/midas-bank-test.js midas

# Calliope Books (route ordering bug)
./scripts/run-prometheus-test.sh k6/calliope-books-test.js calliope

# Hestia Eats (unbounded fetchAll)
./scripts/run-prometheus-test.sh k6/hestia-eats-test.js hestia
```

### Run GraphRAG CLI

```bash
# Extract schemas for changed endpoints from a diff
echo '+@app.post("/api/transactions/transfer")' | python3 -m graphrag \
  --spec demos/midas-bank/openapi.json --diff-stdin
```

Example output:
```
## GraphRAG Traversal

Graph: 52 nodes, 58 edges
Matched endpoints: 1

  ● POST /api/transactions/transfer
    ├─ AUTH → Bearer token required
    ├─ ACCEPTS → TransferRequest (schema)
    │  ├─ .from_account_id: integer *
    │  ├─ .to_account_id: integer *
    │  ├─ .amount: number *
    │  ├─ .description: string
    ├─ RETURNS → TransactionOut (schema)
    │  ├─ .id: integer
    │  ├─ .amount: number
    │  ├─ .type: string

Retrieved: 2 schemas, 0 params, auth=yes
```

### Run tests

```bash
python3 -m pytest tests/ -v
# 43 passed in 0.05s
```

## Demo Applications

Three apps with injected performance faults:

| App | Stack | Port | Injected Bug |
|---|---|---|---|
| Midas Bank | Python / FastAPI / SQLite | 8000 | Shared DB connection — thread-safety fails at 60 VUs |
| Calliope Books | Node / Express / sql.js | 3000 | Route ordering — catch-all before specific route |
| Hestia Eats | TypeScript / Hono / in-memory | 8080 | Unbounded `slice()` — loads all 500+ orders per request |

## Scoring

| Factor | Weight |
|---|---|
| Duration | 20pts |
| Deep sleep ratio | 25pts |

## Project Structure

```
prometheus/
├── graphrag/           # OpenAPI → DiGraph → BFS retrieval (zero deps)
│   ├── builder.py      # Graph construction from OpenAPI 3.x spec
│   ├── retriever.py    # BFS subgraph retrieval + diff parsing
│   ├── digraph.py      # 114-line directed graph, stdlib only
│   └── cli.py          # CLI: python -m graphrag --spec ... --diff-stdin
├── scripts/
│   ├── run-prometheus-test.sh   # Single-invocation: start → k6 → report → cleanup
│   ├── analyze-risk.py          # Pre-test diff scanner (N+1, fetchall, etc.)
│   └── generate-report.py      # Deterministic k6 JSON → Markdown report
├── demos/
│   ├── midas-bank/     # FastAPI + SQLite (thread-safety bug)
│   ├── calliope-books/ # Express + sql.js (route ordering bug)
│   └── hestia-eats/    # Hono + in-memory (unbounded fetchAll)
├── k6/                 # Load test scripts (one per demo app)
├── tests/              # 43 unit + integration tests
└── BOB-CONFIG.md       # IBM Bob prompt and routing table
```

## How IBM Bob Is Used

Bob is the AI brain of the loop. It:

1. **Reads the full repo** — not just the diff. Traces how a changed endpoint connects to the DB layer, middleware, connection pools.
2. **Runs GraphRAG** — `python3 -m graphrag --spec openapi.json --diff-stdin` to get relevant schemas with ~95% token reduction.
3. **Generates the k6 script** — using diff context + GraphRAG schemas + SLOs from `BOB-CONFIG.md`.
4. **Runs the test** — `./scripts/run-prometheus-test.sh <script> <app-type>`.
5. **Interprets results** — root cause analysis grounded in full codebase context. When the SQLite bug causes 60% failures, Bob sees `app.py` line 18 where the shared connection is created.

See `BOB-CONFIG.md` for the full prompt and workflow.

## Built With

- [IBM Bob](https://www.ibm.com/bob) — AI development partner with full repository context
- [Grafana k6](https://k6.io) — open-source load testing (30k+ GitHub stars)
- [FastAPI](https://fastapi.tiangolo.com/) / [Express](https://expressjs.com/) / [Hono](https://hono.dev/) — demo app frameworks
