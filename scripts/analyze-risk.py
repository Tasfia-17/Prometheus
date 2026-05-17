#!/usr/bin/env python3
"""Pre-test risk analysis — scan diffs for performance anti-patterns.

Usage: echo "<diff>" | python3 scripts/analyze-risk.py --diff-stdin
"""
from __future__ import annotations
import re
import sys
from dataclasses import dataclass

@dataclass
class Risk:
    severity: str
    category: str
    description: str
    suggestion: str

PATTERNS = [
    (re.compile(r'(sqlite3\.connect|psycopg2\.connect|mysql\.connector\.connect)\('),
     "no_connection_pool", "medium",
     "DB connection created per-request — no connection pooling",
     "Use a connection pool (SQLAlchemy, psycopg2.pool, etc.)"),
    (re.compile(r'SELECT\s+.*\s+FROM\s+(?!.*LIMIT)', re.IGNORECASE),
     "unbounded_query", "medium",
     "SELECT without LIMIT — may return unbounded result sets",
     "Add LIMIT/OFFSET or pagination"),
    (re.compile(r'\.fetchall\(\)', re.IGNORECASE),
     "unbounded_fetch", "medium",
     "fetchall() loads all rows into memory at once",
     "Use pagination with LIMIT/OFFSET or cursor-based fetching"),
    (re.compile(r'\.slice\(\)'),
     "array_copy", "medium",
     "Unbounded array copy — loads entire dataset into memory",
     "Add pagination: slice(offset, offset+limit)"),
    (re.compile(r'time\.sleep\('),
     "sync_sleep", "high",
     "Synchronous sleep blocks the worker thread",
     "Use async sleep or remove"),
    (re.compile(r'(f"[^"]*(?:SELECT|INSERT|UPDATE|DELETE)|f\'[^\']*(?:SELECT|INSERT|UPDATE|DELETE))', re.IGNORECASE),
     "sql_injection", "high",
     "SQL built with f-string — injection risk and no query plan caching",
     "Use parameterized queries"),
    (re.compile(r'(requests\.(get|post|put|delete)|httpx\.(get|post|put|delete))'),
     "sync_http", "high",
     "Synchronous external HTTP call — latency amplified under load",
     "Use async HTTP client with timeouts"),
    (re.compile(r'for\s+\w+\s+in\s+[^:]+:\s*\n(?:[ \t]+[^\n]*\n)*?[ \t]+for\s+\w+\s+in', re.MULTILINE),
     "nested_loop", "medium",
     "Nested loop — O(n²) complexity degrades under load",
     "Use dicts/sets for O(1) lookups"),
]

DB_CALL = re.compile(r'(\.execute\(|\.query\(|\.find\(|\.filter\(|\.select\()', re.IGNORECASE)
LOOP = re.compile(r'for\s+.+\s+in\s+.+:', re.MULTILINE)


def analyze(diff: str) -> list[Risk]:
    added = "\n".join(
        line[1:] for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    risks, seen = [], set()

    # N+1 detection: DB call anywhere within 10 lines after a loop header
    for m in LOOP.finditer(added):
        context = added[m.end():m.end() + 400]
        if DB_CALL.search(context) and "n_plus_one" not in seen:
            seen.add("n_plus_one")
            risks.append(Risk("high", "n_plus_one",
                              "N+1 query — DB call inside a loop",
                              "Batch queries or use JOINs"))

    for pattern, category, severity, description, suggestion in PATTERNS:
        if category in seen:
            continue
        if pattern.search(added):
            seen.add(category)
            risks.append(Risk(severity, category, description, suggestion))

    risks.sort(key=lambda r: {"high": 0, "medium": 1, "low": 2}.get(r.severity, 3))
    return risks


def format_report(risks: list[Risk]) -> str:
    if not risks:
        return "### 🛡️ Pre-Test Risk Analysis\n\n> No performance anti-patterns detected\n"

    lines = ["### 🛡️ Pre-Test Risk Analysis\n"]
    high = sum(1 for r in risks if r.severity == "high")
    med = sum(1 for r in risks if r.severity == "medium")
    if high:
        lines.append(f"> ⚠️ **{high} high-severity** risk{'s' if high != 1 else ''} detected\n")
    elif med:
        lines.append(f"> 🔍 **{med} medium-severity** risk{'s' if med != 1 else ''} detected\n")

    icons = {"high": "🔴", "medium": "🟡", "low": "🔵"}
    lines += ["| Severity | Risk | Suggestion |", "|---|---|---|"]
    for r in risks:
        lines.append(f"| {icons.get(r.severity, '⚪')} {r.severity.upper()} | {r.description} | {r.suggestion} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    if "--diff-stdin" not in sys.argv:
        print("Usage: analyze-risk.py --diff-stdin < diff.patch", file=sys.stderr)
        sys.exit(1)
    diff = sys.stdin.read()
    if not diff.strip():
        print("No diff provided", file=sys.stderr)
        sys.exit(1)
    print(format_report(analyze(diff)))
