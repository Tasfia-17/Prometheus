# Architecture

Technical deep dive into Prometheus's design — an AI-driven performance testing agent powered by IBM Bob. For usage and results, see [README.md](README.md).

## System Overview

```
Developer asks Bob to test a branch or PR
  │
  ▼
IBM Bob (full repository context)
  │
  1. Read repo + diff
  │   └── Identifies changed route declarations
  │       Bob traces DB layer, middleware, connection pools
  │       (context outside the diff — Bob's key advantage)
  │
  2. Read BOB-CONFIG.md routing table
  │   └── Maps diff paths → demo-specific config (SLOs, auth, exec command)
  │
  3. Run GraphRAG CLI
  │   └── openapi.json → DiGraph → BFS → relevant schemas (~95% token reduction)
  │
  4. Run analyze-risk.py on diff
  │   └── Detects N+1, fetchall(), unbounded SELECTs, sync HTTP calls, etc.
  │
  5. Generate k6 script
  │   └── Open-model executors, per-endpoint SLOs, deep response validation
  │
  6. Write k6/<slug>.js to repo
  │
  7. Run run-prometheus-test.sh (single invocation)
  │   ├── Language-detected app startup (uvicorn / node)
  │   ├── Health check loop (retry until /api/health → 200)
  │   ├── k6 execution (captures JSON via handleSummary)
  │   └── Cleanup via trap EXIT handler
  │
  8. generate-report.py (deterministic — no LLM)
  │   └── k6 JSON → Markdown: threshold table, latency bars, p95 drift vs baseline
  │
  9. Bob interprets results
      └── Root cause analysis grounded in full repo context
          Fix recommendation with file + line reference
```

**Bob's advantage over diff-only agents:** Bob reads the entire repository. When a changed endpoint fails under load, Bob traces the failure to `db.py`, the ORM config, the connection pool setup — context that lives outside the changed files. Root cause analysis is grounded in the full codebase.

---

## OpenAPI GraphRAG

### The Problem with Full-Spec Prompting

Dumping a full OpenAPI spec into Bob's context forces it to chase `$ref` pointers while simultaneously writing a k6 script. The model generates tests for endpoints that exist in the spec but weren't changed. GraphRAG pre-resolves those `$ref` chains into an explicit typed tree — the model gets only the schemas reachable from the changed endpoints.

Result: zero hallucinated endpoints, ~95% fewer tokens.

### Graph Construction (`graphrag/builder.py`)

Parses an OpenAPI 3.x spec into a directed graph.

**Node types:**
- `endpoint` — one per HTTP method + path (e.g., `POST /api/transactions/transfer`)
- `schema` — one per named schema in `components/schemas`
- `property` — one per field on a schema (name, type, required flag)
- `parameter` — one per query/path/header parameter
- `security` — one per security scheme

**Edge types:**
- `RETURNS` — endpoint → schema (response body)
- `ACCEPTS` — endpoint → schema (request body)
- `HAS_PROPERTY` — schema → property
- `REFERENCES` — property → schema (via `$ref`)
- `HAS_PARAM` — endpoint → parameter
- `REQUIRES_AUTH` — endpoint → security scheme

### The DiGraph (`graphrag/digraph.py`)

114-line directed graph, zero external dependencies, standard library only. No NetworkX, no pip install required in the execution environment. Imports in milliseconds.

### BFS Retrieval (`graphrag/retriever.py`)

BFS at **depth 2** from each changed endpoint node:

```
POST /api/transactions/transfer          (depth 0: endpoint)
  ├── ACCEPTS → TransferRequest          (depth 1: schema)
  │     ├── .from_account_id: integer *  (depth 2: property)
  │     ├── .to_account_id: integer *    (depth 2: property)
  │     └── .amount: number *            (depth 2: property)
  ├── RETURNS → TransactionOut           (depth 1: schema)
  │     ├── .id: integer                 (depth 2: property)
  │     └── .type: string               (depth 2: property)
  └── AUTH → Bearer token required
```

Depth 2 was chosen empirically. Depth 1 misses property-level detail needed for response validation. Depth 3 pulls in too many transitive schemas.

### Diff Parsing

Extracts endpoint paths from **added lines only** (lines starting with `+`). Matches route declaration patterns across Python, JavaScript, and TypeScript:

- Python: `@app.get(`, `@app.post(`, `@router.get(`
- JavaScript/TypeScript: `router.get(`, `app.post(`, `app.use(`
- Express path params (`:id`) normalized to OpenAPI template params (`{id}`)

### Measured Token Reduction

| Spec | Nodes | Edges | Full spec (tokens) | GraphRAG (tokens) | Reduction |
|---|---|---|---|---|---|
| Midas Bank | 52 | 58 | ~3,500 | ~180 | ~95% |
| Calliope Books | 44 | 48 | ~2,800 | ~120 | ~96% |
| Hestia Eats | 68 | 74 | ~4,500 | ~220 | ~95% |

---

## Executor Selection

k6 supports open-model and closed-model executor families.

**Closed-model** (`ramping-vus`): each VU waits for the response before sending the next request. When the server slows down, request rate drops — masking the exact regressions you're testing for.

**Open-model** (`constant-arrival-rate`): request rate is maintained regardless of server response time. Latency regressions become visible.

Prometheus exclusively generates open-model executors. This is why the SQLite thread-safety bug is caught — 60 VUs at constant arrival rate exposes the contention that serial testing never sees.

---

## Pre-Test Risk Analysis (`scripts/analyze-risk.py`)

Scans the MR diff before k6 runs. Pattern matching on added lines:

| Pattern | Severity | Example |
|---|---|---|
| N+1 query (DB call inside loop) | High | `for item in items: db.execute(...)` |
| Unbounded SELECT (no LIMIT) | Medium | `SELECT * FROM transactions` |
| `fetchall()` / `slice()` into memory | Medium | Loading all rows before processing |
| Synchronous external HTTP call | High | `requests.get(external_api)` |
| Per-request DB connection | Medium | `sqlite3.connect()` inside handler |
| SQL string formatting | High | `f"SELECT * WHERE id={user_id}"` |
| Synchronous sleep | High | `time.sleep()` in request handler |
| Nested loops (O(n²)) | Medium | `for x in items: for y in items` |

---

## Single-Invocation Execution (`scripts/run-prometheus-test.sh`)

`run_command` blocks until exit. Starting the app in one call and k6 in another leaves the server hung. The entire lifecycle runs in one process:

```
1. Detect app type → install deps
2. Start app server in background (PID tracked)
3. Health check loop — retry until /api/health → 200 (max 15 attempts)
4. Run analyze-risk.py on diff
5. Run GraphRAG CLI on openapi.json
6. Validate k6 script (k6 inspect)
7. Execute k6 — capture JSON via handleSummary()
8. Run generate-report.py on k6 JSON
9. Write report to stdout (fd 3 redirect — only report reaches Bob)
10. Cleanup — kill app server via trap EXIT handler
```

Stdout is split: all operational logs go to `/tmp/prometheus-run.log`. Only the final Markdown report reaches Bob via fd 3.

---

## Report Generation (`scripts/generate-report.py`)

Deterministic Python — no LLM. k6 JSON → Markdown.

**Why deterministic?** Bob produced broken Mermaid charts ~20% of the time when asked to generate them. The only reliable path is deterministic generation from structured data.

**Output:**
- Latency percentile bar chart (`xychart-beta`): min, avg, med, p90, p95, max
- p95 by endpoint (`xychart-beta`)
- Timing breakdown (`pie`): blocked, connecting, sending, TTFB, receiving
- Check results (`pie`): passed vs. failed
- Baseline regression detection: flags >10% p95 drift vs stored baseline

---

## Bob Prompt Design (`BOB-CONFIG.md`)

Structured as a strict numbered checklist to prevent reasoning loops:

1. Read diff + repo context
2. Read routing table
3. Run GraphRAG CLI
4. Run risk analysis
5. Generate k6 script (rules inline)
6. Write script to repo
7. Run `run-prometheus-test.sh`
8. Post report verbatim + root cause analysis

k6 generation rules (executor types, forbidden imports, `handleSummary` format) are inline in the same prompt. GraphRAG keeps spec context under 500 tokens.

---

## Diff-Based Routing

Root `BOB-CONFIG.md` maps diff file paths to demo-specific configs:

```
demos/midas-bank/*     → demos/midas-bank/BOB-CONFIG.md
demos/calliope-books/* → demos/calliope-books/BOB-CONFIG.md
demos/hestia-eats/*    → demos/hestia-eats/BOB-CONFIG.md
```

Same agent, three stacks, zero agent code changes. Only the per-project config differs.

---

## Demo Applications

| App | Stack | Endpoints | Injected Fault |
|---|---|---|---|
| Midas Bank | Python / FastAPI / SQLite | 7 | Shared DB connection — thread-safety fails at 60 VUs |
| Calliope Books | Node / Express / sql.js | 5 | Route ordering — catch-all before specific route |
| Hestia Eats | Node / Hono / in-memory | 7 | `slice()` on 500+ item array — unbounded memory copy |

---

## Test Coverage

43 unit + integration tests across three modules:

| Module | Tests | Coverage |
|---|---|---|
| `test_builder.py` | 15 | Graph construction, node/edge types, property extraction |
| `test_retriever.py` | 17 | BFS traversal, diff parsing, fuzzy matching, path matching |
| `test_integration.py` | 11 | End-to-end: spec → graph → retrieval → text output |

```bash
$ python3 -m pytest tests/ -v
# 43 passed in 0.05s
```

---

## Key Design Decisions

**Bob does what Bob is good at. Python does the rest.**
Bob reads code, traces logic across the full repo, generates k6 scripts, interprets results. Python generates charts deterministically. k6 executes load. Never ask Bob to produce Mermaid syntax — LLM-generated structured syntax breaks ~20% of the time.

**Restructured context beats trimmed context.**
Reducing token count alone wasn't enough. The fix was changing the representation so ambiguity was gone before Bob saw it. GraphRAG pre-resolves `$ref` chains into an explicit typed tree.

**Open-model executors only.**
Closed-model executors hide regressions. `constant-arrival-rate` maintains throughput regardless of server response time.

**Bob's repo context for root cause.**
When k6 reports 60% failure rate, Bob sees the database connection setup, ORM config, middleware stack — not just the changed lines. This is the core differentiator.

---

## Baseline Regression Detection

Stored in `.prometheus/baselines/<app-type>.json`. `generate-report.py` compares current p95 against baseline:

- Within 10%: ✅ no flag
- 10–50% slower: ⚠️ warning
- 50%+ slower: 🔴 regression alert
