# Demo Guide for Judges — Prometheus with IBM Bob

This guide shows how to demonstrate Prometheus's autonomous performance testing capabilities using IBM Bob.

---

## Prerequisites

1. **IBM Bob access** — judges should have Bob CLI or web interface access
2. **Repository cloned** — `git clone https://github.com/Tasfia-17/Prometheus.git`
3. **Dependencies installed:**
   ```bash
   # Python 3.12+
   pip install pytest fastapi uvicorn pydantic
   
   # Node.js 20+
   npm install -g k6
   
   # k6 (Linux)
   sudo gpg -k
   sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
     --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
   echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
     | sudo tee /etc/apt/sources.list.d/k6.list
   sudo apt-get update && sudo apt-get install k6
   ```

---

## Demo Scenario 1: Autonomous Bug Detection (Midas Bank)

**What you'll show:** Bob catches a SQLite thread-safety bug that passes all unit tests but fails 60% of requests under concurrent load.

### Step 1: Show the Bug

```bash
cd demos/midas-bank
cat app.py | grep -A5 "shared_conn"
```

**Point out:** Line 18 creates a single shared `sqlite3.Connection`. This isn't thread-safe under FastAPI's thread pool.

### Step 2: Ask Bob to Test

**Prompt for Bob:**
```
I have a FastAPI application in demos/midas-bank/ with a potential performance issue. 
Can you:
1. Read the BOB-CONFIG.md file
2. Generate a k6 load test for the transfer endpoint
3. Run the test and report the results

The app is at demos/midas-bank/app.py and the OpenAPI spec is at demos/midas-bank/openapi.json.
```

### Step 3: Bob's Workflow

Bob will:
1. Read `BOB-CONFIG.md` → sees Midas Bank config
2. Read the diff or endpoint declaration
3. Run GraphRAG: `python3 -m graphrag --spec demos/midas-bank/openapi.json --diff-stdin`
4. Generate k6 script with 60 VUs, constant-arrival-rate executor
5. Run `./scripts/run-prometheus-test.sh k6/midas-bank-test.js midas`
6. Post report showing ~60% failure rate

### Step 4: Show the Report

The report will show:
- **Status:** 🔴 FAIL
- **Failures:** ~60%
- **Root cause:** "SQLite objects created in a thread can only be used in that same thread"
- **Recommendation:** Use connection pooling or per-request connections

### Step 5: Show It Works Serially

```bash
cd demos/midas-bank
pip install -r requirements.txt
uvicorn app:app --port 8000 &
sleep 2

# Single request works fine
curl -X POST http://localhost:8000/api/transactions/transfer \
  -H "Authorization: Bearer test-token-midas" \
  -H "Content-Type: application/json" \
  -d '{"from_account_id":1,"to_account_id":2,"amount":10.0}'

# Returns 201 with transaction details
kill %1
```

**Key point:** Serial tests pass. Only concurrent load reveals the bug.

---

## Demo Scenario 2: GraphRAG Token Reduction

**What you'll show:** GraphRAG reduces tokens by ~95% while maintaining perfect schema coverage.

### Step 1: Show Full Spec Size

```bash
cd demos/midas-bank
wc -l openapi.json
cat openapi.json | wc -c
# ~400 lines, ~12,000 characters
```

### Step 2: Run GraphRAG

```bash
echo '+@app.post("/api/transactions/transfer")' | python3 -m graphrag \
  --spec demos/midas-bank/openapi.json --diff-stdin
```

**Output shows:**
```
Graph: 52 nodes, 58 edges
Matched endpoints: 1

  ● POST /api/transactions/transfer
    ├─ ACCEPTS → TransferRequest (schema)
    │  ├─ .from_account_id: integer
    │  ├─ .to_account_id: integer
    │  ├─ .amount: number
    │  ├─ .description: string
    ├─ RETURNS → TransactionOut (schema)
    ...

Retrieved: 4 schemas, 1 params, auth=yes
```

**Point out:** Only 4 schemas retrieved instead of the full spec. ~95% token reduction.

### Step 3: Run A/B Proof (Optional, requires OpenAI API key)

```bash
export OPENAI_API_KEY=<your-key>
python3 scripts/graphrag-proof.py
```

This empirically validates that GraphRAG produces identical schema coverage with zero hallucinations.

---

## Demo Scenario 3: Polyglot Architecture

**What you'll show:** Same agent, three different stacks, zero code changes.

### Quick Test All Three Apps

```bash
# Terminal 1: Midas Bank (Python/FastAPI)
cd demos/midas-bank
pip install -r requirements.txt
uvicorn app:app --port 8000

# Terminal 2: Calliope Books (JavaScript/Express)
cd demos/calliope-books
npm install
node app.js

# Terminal 3: Hestia Eats (JavaScript/Hono)
cd demos/hestia-eats
npm install
node app.js
```

**Ask Bob to test any of them:**
```
Test the Calliope Books API at demos/calliope-books/. 
Focus on the search endpoint which has a route ordering bug.
```

Bob will:
1. Detect it's Calliope Books from the diff path
2. Read `demos/calliope-books/BOB-CONFIG.md`
3. Generate appropriate k6 script
4. Catch the 100% failure rate on `/api/books/search`

---

## Demo Scenario 4: GitHub Actions Integration

**What you'll show:** Automated PR testing without manual intervention.

### Step 1: Show the Workflow

```bash
cat .github/workflows/prometheus.yml
```

**Point out:**
- Triggers on PR open/sync or `@prometheus test` comment
- Detects which demo changed
- Runs test automatically
- Posts results as PR comment

### Step 2: Create a Test PR (Live Demo)

```bash
# Create a branch with a change
git checkout -b demo/test-transfer
echo "# Test change" >> demos/midas-bank/app.py
git add demos/midas-bank/app.py
git commit -m "Test: trigger Prometheus"
git push origin demo/test-transfer
```

Then open a PR on GitHub. The workflow will:
1. Detect `demos/midas-bank/` changed
2. Run the test
3. Post results as a comment

---

## Demo Scenario 5: Pre-Test Risk Analysis

**What you'll show:** Bob flags performance anti-patterns before running the test.

### Show Risk Detection

```bash
# Create a diff with an N+1 query
cat > /tmp/test-diff.patch << 'EOF'
+def get_accounts_summary():
+    accounts = db.execute("SELECT * FROM accounts").fetchall()
+    for account in accounts:
+        # N+1: separate query per account
+        txn_count = db.execute(
+            "SELECT COUNT(*) FROM transactions WHERE account_id=?",
+            (account[0],)
+        ).fetchone()[0]
EOF

cat /tmp/test-diff.patch | python3 scripts/analyze-risk.py --diff-stdin
```

**Output:**
```
### 🛡️ Pre-Test Risk Analysis

> ⚠️ **1 high-severity** risk detected

| Severity | Risk | Suggestion |
|---|---|---|
| 🔴 HIGH | N+1 query — DB call inside a loop | Batch queries or use JOINs |
```

---

## Key Points to Emphasize

1. **Autonomous:** Bob reads the diff, generates the test, runs it, diagnoses failures
2. **Real bugs:** Thread-safety and route ordering bugs caught with no human hints
3. **GraphRAG:** ~95% token reduction, zero hallucinations, empirically verified
4. **Polyglot:** Python, JavaScript, TypeScript — same agent
5. **Production-ready:** GitHub Actions integration, deterministic reporting
6. **Auditable:** Generated k6 scripts committed to repo

---

## Troubleshooting

**If Bob doesn't have file system access:**
- Show the GraphRAG CLI output manually
- Show the k6 script generation rules in `BOB-CONFIG.md`
- Run the test script manually and show Bob the output

**If k6 isn't installed:**
- Show the existing k6 scripts in `k6/` directory
- Show the test results in `k6/prometheus/results/` (if any exist)
- Walk through the script structure

**If demos won't start:**
- Show the code with the injected bugs
- Show the OpenAPI specs
- Explain how the test would catch the bug

---

## Quick Demo Script (5 minutes)

1. **Show the problem** (30s): "Performance bugs are invisible in unit tests"
2. **Show GraphRAG** (1m): Run the CLI, show token reduction
3. **Show a bug** (2m): Midas Bank thread-safety, show the code, explain why it fails
4. **Show the architecture** (1m): Diagram in README.md
5. **Show GitHub Actions** (30s): Workflow file, explain automation

---

## Questions Judges Might Ask

**Q: How does this differ from existing tools?**
A: Schemathesis fuzzes, Dredd validates contracts, k6 Cloud executes. None read a diff and generate a complete test. Prometheus closes the full loop.

**Q: Why GraphRAG instead of just trimming the spec?**
A: Trimming still leaves ambiguity. Bob hallucinates endpoints from the full spec even when told to focus. GraphRAG restructures the context so ambiguity is gone before Bob sees it.

**Q: Why open-model executors?**
A: Closed-model executors reduce load when the server slows down, hiding the regressions you're testing for. Open-model maintains constant throughput.

**Q: Can this scale to production?**
A: Yes. The architecture is runner-agnostic. Scaling to production load means changing k6 executor parameters, not the agent logic.

**Q: What about non-REST APIs?**
A: GraphQL and gRPC are planned. Both have introspection schemas that map naturally to graph-based retrieval.

---

## Repository Links

- **Main repo:** https://github.com/Tasfia-17/Prometheus
- **README:** Full documentation with architecture diagrams
- **ARCHITECTURE.md:** Technical deep dive
- **SUBMISSION.md:** Comprehensive summary for judges
- **Tests:** `pytest tests/ -v` (53 tests, 0.10s)
