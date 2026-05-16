#!/usr/bin/env python3
"""Generate a Markdown report from k6 JSON output.

Usage: python3 scripts/generate-report.py <results.json> [--baseline <baseline.json>] [--save-baseline <path>] [--risk-report <path>] [--graphrag-report <path>]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def metric_val(metrics: dict, name: str, stat: str, default=0.0) -> float:
    m = metrics.get(name, {})
    v = m.get("values", {})
    return v.get(stat, default)


def bar_chart(title: str, labels: list[str], values: list[float], unit: str = "ms") -> str:
    if not labels:
        return ""
    lines = [f'```mermaid', f'xychart-beta', f'  title "{title}"',
             f'  x-axis {json.dumps(labels)}',
             f'  y-axis "{unit}"',
             f'  bar {json.dumps([round(v, 2) for v in values])}',
             '```']
    return "\n".join(lines)


def pie_chart(title: str, data: dict[str, float]) -> str:
    lines = ['```mermaid', f'pie title "{title}"']
    for label, val in data.items():
        if val > 0:
            lines.append(f'  "{label}" : {round(val, 2)}')
    lines.append('```')
    return "\n".join(lines)


def generate_report(results_path: str, baseline_path: str | None,
                    save_baseline: str | None, risk_report: str | None,
                    graphrag_report: str | None) -> str:
    data = load_json(results_path)
    metrics = data.get("metrics", {})
    root_group = data.get("root_group", {})

    # ── Core metrics ──
    total_reqs = int(metric_val(metrics, "http_reqs", "count"))
    failed_rate = metric_val(metrics, "http_req_failed", "rate") * 100
    p95 = metric_val(metrics, "http_req_duration", "p(95)")
    p90 = metric_val(metrics, "http_req_duration", "p(90)")
    avg = metric_val(metrics, "http_req_duration", "avg")
    med = metric_val(metrics, "http_req_duration", "med")
    min_d = metric_val(metrics, "http_req_duration", "min")
    max_d = metric_val(metrics, "http_req_duration", "max")
    rps = metric_val(metrics, "http_reqs", "rate")
    checks_pass = metric_val(metrics, "checks", "passes")
    checks_fail = metric_val(metrics, "checks", "fails")
    checks_total = checks_pass + checks_fail
    checks_rate = (checks_pass / checks_total * 100) if checks_total > 0 else 0

    # ── Threshold results ──
    thresholds = data.get("thresholds", {})
    passed = sum(1 for v in thresholds.values() if not v.get("ok") is False)
    total_thresh = len(thresholds)

    # ── Status emoji ──
    if failed_rate > 10:
        status = "🔴 FAIL"
    elif failed_rate > 1:
        status = "🟡 WARN"
    else:
        status = "🟢 PASS"

    lines = [f"# 🔥 Prometheus Performance Report\n",
             f"**Status:** {status} | **Requests:** {total_reqs:,} | **RPS:** {rps:.1f} | "
             f"**Failures:** {failed_rate:.1f}% | **Thresholds:** {passed}/{total_thresh} pass\n"]

    # ── Risk report ──
    if risk_report and Path(risk_report).exists():
        lines.append(Path(risk_report).read_text())
        lines.append("")

    # ── Latency summary ──
    lines.append("## ⏱️ Latency Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Min | {min_d:.1f}ms |")
    lines.append(f"| Avg | {avg:.1f}ms |")
    lines.append(f"| Median | {med:.1f}ms |")
    lines.append(f"| p90 | {p90:.1f}ms |")
    lines.append(f"| p95 | {p95:.1f}ms |")
    lines.append(f"| Max | {max_d:.1f}ms |")
    lines.append("")

    # ── Latency bar chart ──
    lines.append(bar_chart("Latency Percentiles",
                            ["min", "avg", "med", "p90", "p95", "max"],
                            [min_d, avg, med, p90, p95, max_d]))
    lines.append("")

    # ── Baseline regression detection ──
    if baseline_path and Path(baseline_path).exists():
        baseline = load_json(baseline_path)
        baseline_p95 = baseline.get("p95", 0)
        if baseline_p95 > 0:
            drift = (p95 - baseline_p95) / baseline_p95 * 100
            if drift > 50:
                lines.append(f"### 🔴 Regression Alert\np95 is **{drift:.0f}% slower** than baseline ({baseline_p95:.1f}ms → {p95:.1f}ms)\n")
            elif drift > 10:
                lines.append(f"### ⚠️ Performance Warning\np95 is **{drift:.0f}% slower** than baseline ({baseline_p95:.1f}ms → {p95:.1f}ms)\n")
            else:
                lines.append(f"### ✅ No Regression\np95 within 10% of baseline ({baseline_p95:.1f}ms → {p95:.1f}ms, {drift:+.0f}%)\n")

    # ── Save baseline ──
    if save_baseline:
        Path(save_baseline).parent.mkdir(parents=True, exist_ok=True)
        Path(save_baseline).write_text(json.dumps({"p95": p95, "avg": avg, "rps": rps}))

    # ── Threshold table ──
    if thresholds:
        lines.append("## 📊 Threshold Results\n")
        lines.append("| Threshold | Result |")
        lines.append("|---|---|")
        for name, val in thresholds.items():
            ok = val.get("ok", True)
            lines.append(f"| `{name}` | {'✅ PASS' if ok else '❌ FAIL'} |")
        lines.append("")

    # ── Checks ──
    if checks_total > 0:
        lines.append(f"## ✅ Validation Checks\n")
        lines.append(f"**{int(checks_pass):,} passed** / {int(checks_total):,} total ({checks_rate:.1f}%)\n")
        lines.append(pie_chart("Check Results", {"Passed": checks_pass, "Failed": checks_fail}))
        lines.append("")

    # ── Timing breakdown ──
    blocked = metric_val(metrics, "http_req_blocked", "avg")
    connecting = metric_val(metrics, "http_req_connecting", "avg")
    sending = metric_val(metrics, "http_req_sending", "avg")
    waiting = metric_val(metrics, "http_req_waiting", "avg")
    receiving = metric_val(metrics, "http_req_receiving", "avg")
    if any([blocked, connecting, sending, waiting, receiving]):
        lines.append("## 🔬 Request Timing Breakdown (avg)\n")
        lines.append(pie_chart("Request Timing", {
            "Blocked": blocked, "Connecting": connecting,
            "Sending": sending, "TTFB": waiting, "Receiving": receiving
        }))
        lines.append("")

    # ── GraphRAG context ──
    if graphrag_report and Path(graphrag_report).exists():
        lines.append("## 🔍 GraphRAG Context Used\n")
        lines.append("<details><summary>Expand schema context</summary>\n")
        lines.append(Path(graphrag_report).read_text())
        lines.append("</details>\n")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("results", help="k6 JSON results file")
    parser.add_argument("--baseline", help="Baseline JSON for regression detection")
    parser.add_argument("--save-baseline", help="Save current p95 as new baseline")
    parser.add_argument("--risk-report", help="Risk analysis markdown file")
    parser.add_argument("--graphrag-report", help="GraphRAG output markdown file")
    args = parser.parse_args()

    report = generate_report(args.results, args.baseline, args.save_baseline,
                              args.risk_report, args.graphrag_report)

    out_path = args.results.replace(".json", "-report.md")
    Path(out_path).write_text(report)
    print(f"Report written: {out_path}", file=sys.stderr)
    print(report)
