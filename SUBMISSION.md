# Prometheus — Submission Summary

**IBM Bob Hackathon 2026**  
**Repository:** https://github.com/Tasfia-17/Prometheus

---

## Executive Summary

Prometheus is an AI-driven performance testing agent that closes the loop from code diff to load test execution to verdict. Point IBM Bob at a pull request, and it autonomously generates a Grafana k6 load test, runs it against the live application, and posts a performance report with real latency numbers, threshold verdicts, and root cause analysis.

**Key Innovation:** OpenAPI GraphRAG — a novel graph-based retrieval approach that achieves ~95% token reduction while eliminating hallucinated endpoints. A/B verified with empirical proof script.

---

## Technical Highlights

### 1. Autonomous Bug Detection
- **SQLite thread-safety bug** (Midas Bank): 60% failure rate under 60 concurrent VUs, invisible in serial tests
- **Express route ordering bug** (Calliope Books): 100% failure rate, caught autonomously
- **N+1 query patterns** across all three demos, flagged by pre-test risk analysis

### 2. OpenAPI GraphRAG
- **~95% token reduction** across all three demo specs
- **Zero hallucinated endpoints** in 53 unit tests
- **114-line custom DiGraph** implementation (zero dependencies, stdlib only)
- **BFS at depth 2** for optimal schema retrieval
- **A/B proof script** (`scripts/graphrag-proof.py`) for empirical validation

### 3. Polyglot Architecture
- **Python / FastAPI / SQLite** (Midas Bank, 9 endpoints)
- **JavaScript / Express / sql.js** (Calliope Books, 8 endpoints)
- **JavaScript / Hono / in-memory** (Hestia Eats, 9 endpoints)
- Same agent, zero code changes — only per-project config differs

### 4. GitHub Actions Integration
- Automatically triggers on pull requests
- Posts results as PR comments
- Real CI/CD workflow, not just a CLI tool
- See `.github/workflows/prometheus.yml`

### 5. Deterministic Reporting
- k6 JSON → Mermaid Markdown (Python, no LLM)
- Latency percentile charts, timing breakdowns, threshold tables
- Baseline regression detection (flags >10% p95 drift)

---

## Architecture

```
Developer opens PR
  │
  ▼
GitHub Actions trigger
  │
  ▼
IBM Bob (full repository context)
  │
  ├── Read repo + diff ──────────── Identifies changed routes
  ├── Read BOB-CONFIG.md ─────────── Routing table → demo-specific config
  ├── Run GraphRAG CLI ────────────── openapi.json → DiGraph → BFS → relevant schemas
  ├── Run analyze-risk.py ─────────── Diff → N+1, fetchall(), unbounded SELECTs
  ├── Generate k6 script ──────────── Open-model executors, SLO thresholds, validation
  ├── Write k6/<slug>.js ──────────── Script committed to repo
  ├── Run run-prometheus-test.sh ──── App startup → k6 → report → cleanup
  ├── Run generate-report.py ──────── k6 JSON → Mermaid Markdown (deterministic)
  └── Post report as PR comment ───── GitHub Actions posts results
```

---

## Key Metrics

| Metric | Value |
|---|---|
| **Test Coverage** | 53 unit + integration tests |
| **Test Runtime** | 0.10s |
| **Token Reduction** | ~95% (Midas: 52 nodes, Calliope: 44, Hestia: 68) |
| **Hallucinated Endpoints** | 0 across all tests |
| **Demo Apps** | 3 (Python, JavaScript, TypeScript) |
| **Total Endpoints** | 26 across all demos |
| **Lines of Code (GraphRAG)** | 114 (DiGraph), zero dependencies |

---

## What Makes This Different

### vs. Existing Tools
- **Schemathesis:** Schema fuzzing, no load testing
- **Dredd:** Contract validation, no load testing
- **k6 Cloud:** Execution only, no test generation
- **Prometheus:** Full loop — diff → test → execution → verdict

### vs. Manual k6 Scripting
- **Manual:** Write test, maintain test, update test when API changes
- **Prometheus:** Bob reads the diff, generates the test, runs it, posts results

### Key Design Decisions
1. **Open-model executors only** — closed-model hides regressions
2. **Deterministic reporting** — LLMs produce broken Mermaid 20% of the time
3. **Single-invocation execution** — Bob's `run_command` blocks until exit
4. **GraphRAG over full-spec** — restructured context beats trimmed context

---

## Challenges Overcome

1. **Bob's context limits** → Strict numbered checklist + GraphRAG
2. **Process lifecycle** → Single shell script with trap handler
3. **Deterministic reporting** → Python generates Mermaid, not Bob
4. **Polyglot routing** → Diff-path mapping in root `BOB-CONFIG.md`

---

## What I Learned

1. **Restructured context beats trimmed context** — changing representation eliminates ambiguity
2. **Don't let LLMs generate structured syntax** — 80% reliability = 20% broken charts
3. **Lean on battle-tested tools** — k6 handles execution, Bob handles reasoning
4. **Split LLM and deterministic work** — Bob reads/generates, Python charts, k6 executes
5. **Open-model executors matter** — constant load reveals regressions

---

## Future Directions

- **Automated baseline comparison** — auto-run on merge to main
- **Multi-protocol support** — GraphQL introspection, gRPC reflection
- **SLO alerting** — auto-create GitHub issues on regression
- **Community adoption** — publish `BOB-CONFIG.md` convention
- **Cross-model validation** — test with local models (Llama, Qwen)

---

## Repository Structure

```
.github/workflows/prometheus.yml  # GitHub Actions integration
BOB-CONFIG.md                     # IBM Bob prompt + routing
ARCHITECTURE.md                   # Technical deep dive
README.md                         # Full documentation

graphrag/                         # OpenAPI GraphRAG (zero deps)
  digraph.py                      # 114-line custom graph
  builder.py                      # OpenAPI → graph
  retriever.py                    # BFS retrieval + diff parsing
  cli.py                          # CLI entry point

scripts/
  run-prometheus-test.sh          # Full test lifecycle
  generate-report.py              # k6 JSON → Mermaid
  analyze-risk.py                 # Pre-test risk analysis
  graphrag-proof.py               # A/B validation script

demos/
  midas-bank/                     # Python/FastAPI (9 endpoints)
  calliope-books/                 # JavaScript/Express (8 endpoints)
  hestia-eats/                    # JavaScript/Hono (9 endpoints)

k6/                               # Generated load tests
tests/                            # 53 unit tests
```

---

## Running Locally

```bash
# Unit tests
python3 -m pytest tests/ -v
# 53 passed in 0.10s

# GraphRAG CLI
echo '+@app.post("/api/transactions/transfer")' | python3 -m graphrag \
  --spec demos/midas-bank/openapi.json --diff-stdin

# GraphRAG A/B proof
export OPENAI_API_KEY=<your-key>
python3 scripts/graphrag-proof.py

# Demo apps
cd demos/midas-bank && pip install -r requirements.txt && uvicorn app:app --port 8000
cd demos/calliope-books && npm install && node app.js
cd demos/hestia-eats && npm install && node app.js

# Run a load test
./scripts/run-prometheus-test.sh k6/midas-bank-test.js midas
```

---

## License

MIT

---

**Built with IBM Bob for the IBM Bob Hackathon 2026**  
**Repository:** https://github.com/Tasfia-17/Prometheus
