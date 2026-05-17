# Prometheus

AI performance testing agent powered by IBM Bob. Point Bob at any repo, ask it to test a branch — it reads the diff, generates a [Grafana k6](https://k6.io/) load test, executes it against the live application, and posts a performance report with real latency numbers, threshold verdicts, and root cause analysis. No test authoring. No CI configuration. One config file per project.

Built with [IBM Bob](https://www.ibm.com/bob) for the [IBM Bob Hackathon 2026](https://lablab.ai/event/ibm-bob-hackathon).

> *Prometheus stole fire from the gods and gave it to mortals. This Prometheus steals performance regressions from production and gives the verdict to developers — before the merge.*

---

## Summary

Prometheus is the full loop: **diff → test → execution → verdict**. It generates a k6 load test, deploys the application, runs concurrent virtual users against it, and reports what actually happened under load. Real latency numbers. Real pass/fail thresholds. Real bugs caught.

**GitHub Actions integration:** Automatically triggers on pull requests, posts results as PR comments. See [`.github/workflows/prometheus.yml`](.github/workflows/prometheus.yml).

**Key features:**
- Autonomous bug detection: catches thread-safety issues, route ordering bugs, N+1 queries
- OpenAPI GraphRAG: ~95% token reduction, zero hallucinated endpoints, A/B verified
- Polyglot: Python/FastAPI, JavaScript/Express, TypeScript/Hono — same agent, zero code changes
- 53 unit tests, deterministic report generation, open-model executors only

---

## Why Performance Testing Matters

Some bugs only appear under load. A SQLite endpoint that passes every unit test can fail 60% of requests when concurrent users hit it, because thread-safety constraints only surface under real concurrency. Unit tests verify logic. Load tests verify behavior under production conditions. They catch different classes of bugs.

**The cost of skipping load testing is well-documented:**
- Amazon found that every [100ms of latency costs 1% in sales](https://www.gigaspaces.com/blog/amazon-found-every-100ms-of-latency-cost-them-1-in-sales/)
- Unplanned downtime averages [$14,056 per minute](https://www.erwoodgroup.com/blog/the-true-costs-of-downtime-in-2025-a-deep-dive-by-business-size-and-industry/)

**Companies that do load test see the difference:**
- **fuboTV** uses Grafana k6 to catch performance regressions before production during high-traffic sporting events
- **Olo** processes millions of restaurant orders per day and integrated k6 into their CI/CD pipeline so every release is verified under load before deployment

The pattern is the same: teams that test under load find bugs before users do. Teams that don't, don't.

**But performance testing doesn't scale with development velocity.** [Grafana k6](https://k6.io/) is best-in-class for load testing ([30k+ GitHub stars](https://github.com/grafana/k6), cloud native, scriptable), but writing and maintaining test scripts compounds the gap. Teams ship endpoints faster than they can test them.

No existing tool closes the full loop: read a diff → generate a targeted load test → run it → post results. [Schemathesis](https://schemathesis.io/) does schema fuzzing. [Dredd](https://dredd.org/) does contract validation. k6 Cloud handles execution. None of them read a diff and produce a complete runnable test.

**This is where IBM Bob fits.** Generating a correct k6 script from a code diff requires understanding endpoint semantics, choosing appropriate request bodies, writing validation logic for response schemas, and deciding what a reasonable SLO looks like for each endpoint type. That's a language understanding and code generation problem.

---

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
| Midas Bank | 52 | 58 | **~95%** |
| Calliope Books | 44 | 48 | **~96%** |
| Hestia Eats | 68 | 74 | **~95%** |

Zero hallucinated endpoints across all test scenarios. 53 unit tests, 0.10s runtime.

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

### Why These Bugs Matter

**Midas Bank (Thread-Safety):** FastAPI runs requests in a thread pool. A single shared `sqlite3.Connection` isn't thread-safe. Under 60 concurrent VUs, the endpoint fails ~60% of requests with `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`. Serial tests never see this because there's no contention.

**Calliope Books (Route Ordering):** Express matches routes in registration order. When `GET /api/books/:id` is declared before `GET /api/books/search`, Express treats "search" as an `:id` parameter → 404 for every search request. Unit tests call handlers directly, bypassing Express's route matching, so the bug is invisible until load testing hits the actual HTTP layer.

**Hestia Eats (Unbounded Fetch):** `orders.slice()` copies all 500+ orders into memory on every request. Serial tests are fast enough that this doesn't matter. Under concurrent load with a large dataset, memory pressure accumulates and latency spikes.

---

## Inspiration

Prometheus takes [Grafana k6](https://k6.io/) to its logical extreme: an AI agent writes the test from the code diff. k6 is battle-tested (30k+ GitHub stars, used by fuboTV, Olo, and thousands of teams), cloud native, and scriptable. Prometheus's job is to generate the right script and interpret the results, not reinvent the load testing engine.

The name comes from Greek mythology. Prometheus stole fire from the gods and gave it to mortals. This Prometheus steals performance regressions from production and gives the verdict to developers — before the merge.

---

## Demo Applications

Three sample applications built for this hackathon, each with intentional performance anti-patterns:

| App | Stack | Port | Endpoints | Injected Fault |
|---|---|---|---|---|
| Midas Bank | Python / FastAPI / SQLite | 8000 | 9 | Shared `sqlite3.Connection` — not thread-safe under FastAPI's thread pool; N+1 in accounts summary |
| Calliope Books | JavaScript / Express / sql.js | 3000 | 8 | `GET /api/books/:id` declared before `/api/books/search` — shadows the search route; N+1 in suggestions |
| Hestia Eats | JavaScript / Hono / in-memory | 8080 | 9 | `orders.slice()` copies all 500+ orders into memory on every request; N+1 in restaurant search |

Each app uses production frameworks and real database layers (SQLite, sql.js, in-memory stores), with authentication, pagination, and 8–9 endpoints per app. Zero external dependencies. Each includes a `BOB-CONFIG.md` with project-specific SLOs and auth config, and an `openapi.json` spec.

**The polyglot setup is deliberate:** it demonstrates that Prometheus generalizes across entirely different stacks, not just endpoints within a single app. Same agent, three stacks, zero code changes — only the per-project config differs.

---

## Challenges I Ran Into

**1. Bob's context limits:** Long prompts cause reasoning loops. Structuring the prompt as a strict numbered checklist with inline k6 generation rules, and keeping dynamic context minimal via GraphRAG, was the key fix.

**2. Process lifecycle:** Bob's `run_command` blocks until exit. Starting the app in one call and k6 in another leaves the server hung. A single shell script with a trap handler solved it: app startup, health check, risk analysis, GraphRAG, k6, report generation, cleanup — all in one process.

**3. Deterministic reporting:** Bob produced broken Mermaid charts ~20% of the time. Report generation is now a deterministic Python script: k6 JSON → Markdown with color-themed bar and pie charts. Bob reasons. Python charts. k6 executes.

**4. Polyglot routing:** Bob initially tested whichever demo app it found first. Diff-path routing fixed this: the root `BOB-CONFIG.md` maps file paths in the diff to the correct project config.

---

## Accomplishments I'm Proud Of

✅ **Autonomous bug detection:** SQLite thread-safety under load and Express route ordering. Root causes diagnosed, fixes recommended, no human intervention.

✅ **OpenAPI GraphRAG:** A novel approach to structured API context for LLMs. ~95% token reduction, zero hallucinated endpoints, A/B verified with empirical proof script. 114 lines, zero dependencies, 53 tests.

✅ **Polyglot:** Python, JavaScript, TypeScript. Three stacks, same agent, zero code changes.

✅ **GitHub Actions integration:** Automatically triggers on PRs, posts results as comments. Real CI/CD workflow, not just a CLI tool.

✅ **Auditable by design:** Generated k6 scripts are committed to the repo. Every test is reproducible.

---

## What I Learned

**Restructured context beats trimmed context.** I expected that reducing token count would be enough. It wasn't. Bob hallucinated endpoints from the full spec even when the prompt said "only test changed endpoints." The fix wasn't fewer tokens; it was changing the representation so the ambiguity was gone before Bob saw it.

**Don't let the LLM generate structured syntax.** Mermaid, YAML, k6 thresholds. 80% reliability means 20% broken charts. I wasted time prompt-engineering around this before accepting that deterministic generation from structured data is the only reliable path.

**Lean on battle-tested tools.** Bob's job is to generate the right script and interpret the results, not reinvent the load testing engine. k6 handles the hard parts.

**Split LLM and deterministic work explicitly.** Bob reads diffs and generates k6 scripts. Python charts. k6 executes. Every time I let Bob cross into deterministic territory (Mermaid syntax, threshold arithmetic), reliability dropped.

**Open-model executors matter.** Closed-model executors (`ramping-vus`) reduce throughput when the server slows down, hiding the regressions you're testing for. Prometheus exclusively generates open-model executors (`constant-arrival-rate`) that maintain consistent load regardless of server response time.

---

## What's Next for Prometheus

🔮 **Automated baseline comparison:** The latency data already contains regression signal. `generate-report.py` flags >10% p95 drift against stored baselines. Next step: auto-run on merge to main to build those baselines.

🔮 **Multi-protocol support:** GraphQL's introspection schema is natively graph-structured, making it a natural fit for the same BFS retrieval approach. gRPC reflection similarly.

🔮 **SLO alerting:** Auto-create GitHub issues when performance degrades across runs.

🔮 **Community adoption:** Publish the `BOB-CONFIG.md` convention so any project can onboard with one file.

🔮 **Cross-model validation:** The deterministic GraphRAG retrieval is model-agnostic. Test with local models (Llama, Qwen) to prove portability.

---

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

For **GitHub integration**, Prometheus includes a GitHub Actions workflow that automatically triggers on PRs and posts results as comments. See [`.github/workflows/prometheus.yml`](.github/workflows/prometheus.yml).

**Manual config** (one `BOB-CONFIG.md` per project):

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
# 53 passed in 0.10s

# GraphRAG CLI
echo '+@app.post("/api/transactions/transfer")' | python3 -m graphrag \
  --spec demos/midas-bank/openapi.json --diff-stdin

# GraphRAG A/B proof (requires OpenAI API key)
export OPENAI_API_KEY=<your-key>
python3 scripts/graphrag-proof.py

# Demo apps
cd demos/midas-bank && pip install -r requirements.txt && uvicorn app:app --port 8000
cd demos/calliope-books && npm install && node app.js
cd demos/hestia-eats && npm install && node app.js

# Run a load test
./scripts/run-prometheus-test.sh k6/midas-bank-test.js midas
```

## License

MIT
