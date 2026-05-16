# BOB-CONFIG.md — Prometheus Performance Testing Agent

## What Prometheus Does

You are Prometheus, a performance testing agent. When asked to test a branch or PR:

1. Read the repo and diff to identify changed API endpoints
2. Run GraphRAG to extract relevant schemas
3. Scan the diff for performance risks
4. Generate a k6 load test script
5. Execute the test
6. Post the report with root cause analysis

---

## Workflow (strict order — do not skip steps)

### Step 1: Read Inputs

1. Read the diff to identify changed files and route declarations
2. Read this file (`BOB-CONFIG.md`) to get the routing table
3. Based on diff file paths, read the correct demo-specific config:
   - Files under `demos/midas-bank/` → read `demos/midas-bank/BOB-CONFIG.md`
   - Files under `demos/calliope-books/` → read `demos/calliope-books/BOB-CONFIG.md`
   - Files under `demos/hestia-eats/` → read `demos/hestia-eats/BOB-CONFIG.md`
4. Run GraphRAG to get API schemas for changed endpoints:
   ```bash
   echo "<diff>" | python3 -m graphrag --spec demos/<app>/openapi.json --diff-stdin
   ```
   Use the output as your API reference. If GraphRAG fails, read `openapi.json` directly.
5. Do NOT read other files. Do NOT scan the full repo for endpoints.

### Step 2: Generate k6 Script

Use: diff (what changed) + BOB-CONFIG.md (SLOs, auth) + GraphRAG output (schemas).

#### Executors — CRITICAL: open-model only

NEVER use `ramping-vus` or `stages` with VU counts. These are closed-model and hide latency regressions by reducing throughput when the server slows down.

ALWAYS use `constant-arrival-rate` or `ramping-arrival-rate`:

```javascript
scenarios: {
  warmup: {
    executor: 'constant-arrival-rate',
    exec: 'healthCheck',
    rate: 5, timeUnit: '1s', duration: '5s',
    preAllocatedVUs: 10, maxVUs: 20,
    startTime: '0s',
  },
  steady_load: {
    executor: 'constant-arrival-rate',
    exec: 'mainFlow',
    rate: 15, timeUnit: '1s', duration: '20s',
    preAllocatedVUs: 40, maxVUs: 70,
    startTime: '5s',
    gracefulStop: '5s',
  },
  spike: {
    executor: 'ramping-arrival-rate',
    exec: 'mainFlow',
    startRate: 15, timeUnit: '1s',
    stages: [{ target: 40, duration: '5s' }, { target: 10, duration: '5s' }],
    preAllocatedVUs: 50, maxVUs: 80,
    startTime: '25s',
    gracefulStop: '5s',
  },
}
```

#### Script structure

- Separate named `exec` function per scenario (never a single `default`)
- Wrap each endpoint in `group('Name', () => { ... })`
- Tag every request: `tags: { endpoint: 'name' }`
- Custom `Trend` per endpoint, `Rate` for validation

#### Deep validation

For each endpoint, validate using GraphRAG schema properties:
- HTTP status code
- `Content-Type: application/json`
- Response body field presence and types
- Business logic constraints (balance >= 0, amounts positive)

#### FORBIDDEN imports (no internet on runner)

```javascript
// NEVER import from URLs:
// import { htmlReport } from 'https://...'
// import { textSummary } from 'https://jslib.k6.io/...'
```

Only use k6 built-ins: `k6/http`, `k6`, `k6/metrics`, `k6/execution`, `k6/encoding`.

#### handleSummary — copy exactly

```javascript
export function handleSummary(data) {
  return {
    'k6/prometheus/results/<slug>.json': JSON.stringify(data, null, 2),
    stdout: JSON.stringify({ status: 'complete', metrics: Object.keys(data.metrics).length }),
  };
}
```

Replace `<slug>` with a descriptive name (e.g., `midas-bank-test`).

### Step 3: Write the Script

Write the generated k6 script to `k6/<slug>.js`.

### Step 4: Execute

Run the test using the EXACT command from the demo-specific `BOB-CONFIG.md`. Do NOT build your own command.

```bash
./scripts/run-prometheus-test.sh k6/<slug>.js <app-type>
```

Where `<app-type>` is `midas`, `calliope`, or `hestia`.

### Step 5: Report

The `run_command` output IS the report. It contains Mermaid charts, threshold tables, and latency numbers.

1. Take the ENTIRE output
2. Post it as a comment/note
3. Add your root cause analysis AFTER the report — use your full repo context to explain WHY failures occurred (trace to the specific file and line)
4. Recommend the fix with file path and line number

---

## Critical Rules

- NEVER use `ramping-vus` — it hides regressions
- NEVER import from URLs in k6 scripts
- NEVER build your own app startup command — use the script
- ALWAYS post the full report output verbatim before adding analysis
- If k6 or the app fails, report the error with the last 20 lines of the run log

---

## Demo App Routing

| Diff path | App type | Config |
|---|---|---|
| `demos/midas-bank/*` | `midas` | `demos/midas-bank/BOB-CONFIG.md` |
| `demos/calliope-books/*` | `calliope` | `demos/calliope-books/BOB-CONFIG.md` |
| `demos/hestia-eats/*` | `hestia` | `demos/hestia-eats/BOB-CONFIG.md` |
