# Prometheus vs Kassandra — Feature Comparison

Both projects solve the same problem: autonomous performance testing from code diffs. Here's how they compare:

## Core Features

| Feature | Prometheus | Kassandra |
|---|---|---|
| **Platform** | IBM Bob + GitHub Actions | GitLab Duo Workflow |
| **Trigger** | PR opened/updated or `@prometheus test` comment | `@ai-kassandra` mention on MR |
| **Test Engine** | Grafana k6 | Grafana k6 |
| **Token Reduction** | ~95% (GraphRAG) | ~95% (GraphRAG) |
| **Hallucinated Endpoints** | 0 | 0 |
| **Test Coverage** | 53 tests | 57 tests |
| **Demo Apps** | 3 (Python, JS, TS) | 3 (Python, JS, TS) |
| **Total Endpoints** | 26 | 47 |
| **Autonomous Bug Detection** | ✅ (2 bugs caught) | ✅ (2 bugs caught) |
| **GitHub/GitLab Integration** | ✅ GitHub Actions | ✅ Duo Workflow |
| **A/B Proof Script** | ✅ `graphrag-proof.py` | ✅ `graphrag-proof.py` + Qwen validation |

## Architecture Similarities

Both use:
- **OpenAPI GraphRAG** with custom DiGraph (114 lines, zero deps)
- **BFS at depth 2** for schema retrieval
- **Open-model executors only** (constant-arrival-rate)
- **Deterministic report generation** (Python, not LLM)
- **Single-invocation execution** (app + k6 + cleanup in one script)
- **Diff-based routing** (per-project config files)

## Key Differences

### Prometheus Advantages
- **GitHub Actions integration** — works with GitHub PRs out of the box
- **Simpler setup** — one workflow file, no platform-specific agent config
- **Broader platform support** — can run anywhere Bob runs

### Kassandra Advantages
- **More demo endpoints** — 47 vs 26 (more comprehensive testing)
- **More test coverage** — 57 vs 53 tests
- **Cross-model validation** — tested with Qwen 2.5 7B locally
- **Real MR history** — 23 completed runs documented with MR links
- **More detailed results** — aggregate metrics across all runs

## Technical Deep Dive

Both projects independently arrived at the same core insights:

1. **GraphRAG is essential** — full-spec prompting causes hallucinations
2. **Deterministic reporting is mandatory** — LLMs break structured syntax
3. **Open-model executors reveal regressions** — closed-model hides them
4. **Single-invocation execution** — platform constraints force this design

## Conclusion

Prometheus and Kassandra are parallel implementations of the same architecture on different platforms. The core innovation (OpenAPI GraphRAG) and design decisions (deterministic reporting, open-model executors) are identical because they solve the same fundamental constraints.

**Choose Prometheus if:** You use GitHub and want GitHub Actions integration.

**Choose Kassandra if:** You use GitLab and want Duo Workflow integration.

Both demonstrate that AI-driven performance testing is viable, and both prove that GraphRAG eliminates hallucinations while reducing tokens by ~95%.
