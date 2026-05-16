# Prometheus

AI performance testing agent powered by IBM Bob. Point Bob at any repo, ask it to test a branch — it reads the diff, generates a [Grafana k6](https://k6.io/) load test, executes it against the live application, and posts a performance report with real latency numbers, threshold verdicts, and root cause analysis. No test authoring. No CI configuration. One config file per project.

Built with [IBM Bob](https://www.ibm.com/bob) for the [IBM Bob Hackathon 2026](https://lablab.ai/event/ibm-bob-hackathon).

> *Prometheus stole fire from the gods and gave it to mortals. This Prometheus steals performance regressions from production and gives the verdict to developers — before the merge.*

## The Problem

Performance testing doesn't scale with development velocity. [Grafana k6](https://k6.io/) is best-in-class for load testing ([30k+ GitHub stars](https://github.com/grafana/k6), cloud native, scriptable), but writing and maintaining test scripts compounds the gap. Teams ship endpoints faster than they can test them.

The result: latency regressions ship to production. An N+1 query that adds 200ms per request under load goes unnoticed until customers complain. Amazon found that every [100ms of latency costs 1% in sales](https://www.gigaspaces.com/blog/amazon-found-every-100ms-of-latency-cost-them-1-in-sales/). Unplanned downtime averages [$14,056 per minute](https://www.erwoodgroup.com/blog/the-true-costs-of-downtime-in-2025-a-deep-dive-by-business-size-and-industry/).

No existing tool closes the full loop: read a diff → generate a targeted load test → run it → post results. [Schemathesis](https://schemathesis.io/) does schema fuzzing. [Dredd](https://dredd.org/) does contract validation. k6 Cloud handles execution. None of them read a diff and produce a complete runnable test.

## What Prometheus Does

Ask IBM Bob to performance-test a branch. Bob:

1. Reads the full repo and diff to identify new/changed API endpoints from route declarations
2. Routes to the correct project config via diff file paths
3. Retrieves relevant API schemas via OpenAPI GraphRAG (~95% input token reduction)
4. Scans the diff for performance anti-patterns (N+1 queries, unbounded SELECTs, missing pagination)
5. Generates a k6 script with [open-model executors](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/), per-endpoint SLO thresholds, deep response validation
6. Writes the test to the repo
7. Starts the app, runs k6, shuts everything down
8. Posts a performance report with Mermaid charts, threshold tables, regression detection
9. Adds root cause analysis grounded in full repository context — traces failures to the specific file and line

No CI YAML changes. No per-project agent code. One `BOB-CONFIG.md` per project.

**IBM Bob's key advantage:** Bob reads the entire repository, not just the diff. When k6 reports 60% failure rate, Bob traces the failure to `db.py` line 18 where the shared connection is created — context that lives outside the changed files. Root cause analysis grounded in the full codebase.

## OpenAPI GraphRAG

Feeding a full OpenAPI spec to the LLM wastes context and produces worse tests. The model hallucinates endpoints that exist in the spec but weren't changed. Prometheus solves this with a deterministic knowledge graph built from the spec's [`$ref` structure](https://swagger.io/docs/specification/v3_0/using-ref/) using a zero-dependency custom `DiGraph` implementation (114 lines, stdlib only).

When a branch changes an endpoint, [BFS traversal](https://en.wikipedia.org/wiki/Breadth-first_search) at depth 2 collects only the schemas reachable from that endpoint.

| Spec | Nodes | Edges | Token reduction |
|---|---|---|---|
| Midas Bank | 32 | 30 | **~95%** |
| Calliope Books | 39 | 40 | **~96%** |
| Hestia Eats | 55 | 57 | **~95%** |

Zero hallucinated endpoints across all test scenarios. 43 unit tests, 0.13s runtime.

```
$ echo '+@app.post("/api/transactions/transfer")' | python3 -m graphrag \
    --spec demos/midas-bank/openapi.json --diff-stdin

## GraphRAG Traversal

Graph: 32 nodes, 30 edges
Matched endpoints: 1

  ● POST /api/transactions/transfer
    ├─ AUTH → Bearer token required
    ├─ ACCEPTS → TransferRequest (schema)
    │  ├─ .from_account_id: integer *
    │  ├─ .to_account_id: integer *
    │  ├─ .amount: number *
    │  ├─ .description: string
    ├─ RETURNS → HTTPValidationError (schema)
    │  ├─ .detail: array<ValidationError>

Retrieved: 3 schemas, 1 params, auth=yes
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical deep dive.

## Results

Three demo apps, each with an injected performance fault that passes all serial unit tests but fails under concurrent load:

| App | Bug | VUs | Failure Rate | Outcome |
|---|---|---|---|---|
| Midas Bank | SQLite shared connection (thread-safety) | 60 | ~60% | **Bug caught** |
| Calliope Books | Route ordering (catch-all before specific) | 55 | 100% on search | **Bug caught** |
| Hestia Eats | Unbounded `slice()` on 500+ item array | 60 | Latency spike | **Risk flagged** |

Both coarse failures (Midas Bank, Calliope Books) are invisible in serial testing and obvious under concurrent load. Prometheus diagnosed the root cause autonomously using Bob's full repository context.

## Demo Applications

Three sample applications built for this hackathon, each with intentional performance anti-patterns:

| App | Stack | Port | Endpoints | Injected Fault |
|---|---|---|---|---|
| Midas Bank | Python / FastAPI / SQLite | 8000 | 7 | Shared `sqlite3.Connection` — not thread-safe under FastAPI's thread pool |
| Calliope Books | JavaScript / Express / sql.js | 3000 | 5 | `GET /api/books/:id` declared before `/api/books/search` — shadows the search route |
| Hestia Eats | JavaScript / Hono / in-memory | 8080 | 7 | `orders.slice()` copies all 500+ orders into memory on every request |

Each app includes a `BOB-CONFIG.md` with project-specific SLOs and auth config, and an `openapi.json` spec. Same agent, three stacks, zero code changes — only the per-project config differs.

## Architecture

```
Developer asks Bob to test a branch
  │
  ▼
IBM Bob (full repository context)
  │
  ├── Read repo + diff ──────────── Identifies changed routes, traces DB layer
  │
  ├── Read BOB-CONFIG.md ─────────── Routing table → demo-specific config
  │
  ├── Run GraphRAG CLI ────────────── openapi.json → DiGraph → BFS → relevant schemas
  │
  ├── Run analyze-risk.py ─────────── Diff → N+1, fetchall(), unbounded SELECTs
  │
  ├── Generate k6 script ──────────── Open-model executors, SLO thresholds, validation
  │
  ├── Write k6/<slug>.js ──────────── Script committed to repo
  │
  ├── Run run-prometheus-test.sh ──── App startup → k6 → report → cleanup
  │
  ├── Run generate-report.py ──────── k6 JSON → Mermaid Markdown (deterministic)
  │
  └── Post report + root cause ────── Full codebase context → file + line reference
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions and technical details.

### Project Structure

```
BOB-CONFIG.md                 # IBM Bob prompt + routing table
ARCHITECTURE.md               # Technical deep dive

graphrag/                     # OpenAPI GraphRAG module (zero external deps)
  digraph.py                  # Custom directed graph (114 lines, stdlib only)
  builder.py                  # OpenAPI spec → directed graph
  retriever.py                # BFS subgraph retrieval + diff parsing
  cli.py                      # CLI: python3 -m graphrag --spec ... --diff-stdin

scripts/
  run-prometheus-test.sh      # Full test lifecycle (app + k6 + cleanup)
  generate-report.py          # k6 JSON → Mermaid Markdown report (deterministic)
  analyze-risk.py             # Pre-test code risk analysis from diff

demos/
  midas-bank/                 # Python / FastAPI / SQLite (thread-safety bug)
  calliope-books/             # JavaScript / Express / sql.js (route ordering bug)
  hestia-eats/                # JavaScript / Hono / in-memory (unbounded fetchAll)

k6/                           # Generated load test scripts
tests/                        # 43 unit + integration tests for GraphRAG
```

## Adding Prometheus to Your Project

One file: `BOB-CONFIG.md`. No CI YAML. No SDK. No pipeline changes.

```markdown
# MyApp — BOB-CONFIG.md

## App Info
- Stack: Node.js / Express / PostgreSQL
- Port: 3000
- Auth: Authorization: Bearer test-token

## SLOs
- Default: p95 < 500ms
- Search: p95 < 800ms

## Execution Command
./scripts/run-prometheus-test.sh k6/<slug>.js myapp
```

Add an `openapi.json` spec and Prometheus handles the rest.

## Running Locally

```bash
# Unit tests
python3 -m pytest tests/ -v
# 43 passed in 0.13s

# GraphRAG CLI
echo '+@app.post("/api/transactions/transfer")' | python3 -m graphrag \
  --spec demos/midas-bank/openapi.json --diff-stdin

# Demo apps
cd demos/midas-bank && pip install -r requirements.txt && uvicorn app:app --port 8000
cd demos/calliope-books && npm install && node app.js
cd demos/hestia-eats && npm install && node app.js

# Run a load test
./scripts/run-prometheus-test.sh k6/midas-bank-test.js midas
```

## License

MIT
