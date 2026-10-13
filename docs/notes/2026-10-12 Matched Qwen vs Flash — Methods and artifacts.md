---
type: methodology
category: Benchmarks
date: 2026-10-12
updated: 2026-10-12
tags: [benchmark, methodology, deepswe2, audit, reproducibility]
---

# 2026-10-12 Matched Qwen vs Flash — Methods and artifacts

**Findings and embedded charts:** [2026-10-12 Matched Qwen 27B vs Flash DeepSWE2](2026-10-12%20Matched%20Qwen%2027B%20vs%20Flash%20DeepSWE2.md) · **Hub:** Model Benchmarks

The vault contains the full comparison report, both PNG/SVG charts, all six raw campaign outputs and logs, final and superseded audits, checker/fixture snapshots, launch and hardware provenance, and the operational documentation and analysis-source snapshots. The native originals remain in `/home/USER/bench/results` and `/home/USER/bench`. Vault snapshots live in `assets/qwen27b-flash-matched-20261012-165802/`.

## Experimental contract

Run the 24 corrected synthetic DeepSWE2 repository tasks three times per model, producing 144 recorded results over 24 distinct problems. Both lanes used frozen **contract-v2**, complete repository source in every prompt, hidden checks excluded, medium reasoning, temperature zero, and identical task budgets, request timeouts and truncation escalation rules. Paired request seeds were 40, 41 and 42; task-specific seeds would take precedence if present. The served templates were verified to honor medium reasoning. Strata uses greedy decoding at temperature zero and does not forward a random seed in that mode; repeat variation is not seed-driven sampling variance.

The initial task cap was 16,384 tokens, with the frozen escalation ladder 24,576 → 49,152 → 98,304 for unsuccessful length-limited outputs. Request timeout was 5,400 seconds; grader timeouts remained task-specific. All 144 scored requests completed with their initial cap, a single attempt, final content, and no request error or truncation. Full final answers, reasoning, effective seeds/budgets, timing and response/attempt histories remain in the raw files.

Campaign order: **Qwen-40 → Flash-40 → Flash-41 → Qwen-41 → Qwen-42 → Flash-42**. Every campaign started in a fresh server process on dedicated localhost ports (Qwen 18080, Flash 18081). No hosted-model calls or tuning occurred during scoring.

Qwen used Swift Qwen3.8 27B Q5_K_M through llama.cpp build 10809, RX 9060 XT plus RTX 3060, context 131,072, q4_0 KV and MTP n=2. Flash used Qwen3.8-Flash-Next GSQ-RCO IQ3_XXS through UnbiasedStrata, RTX 3060 plus CPU, 12 threads, context 196,608, int8 KV with resident window 32,768 and speculation 4. The machine was a Ryzen 9 7950X with about 62 GiB RAM. Actual arguments, executable hashes, model-file metadata and hardware/driver records are archived.

Ornith was stopped without changing its persistent configuration, was not restored automatically, and remained inactive throughout and afterward. Benchmark servers were stopped after scoring. An initial launch (`165741`) failed before scoring because an empty Vulkan visibility variable hid the requested devices; the corrected launch unsets it, with Vulkan1 = RX 9060 XT and Vulkan2 = RTX 3060. That failed-launch manifest is retained separately.

## Grading and analysis

Corrected-suite self-tests checked known-good implementations, broken fixtures and deliberately broken mutants before inference. Every campaign contains 24 unique task rows, with identical task/message/check fingerprints across all six. Recorded failures were preserved, with no failure retries or best-of-three selection. Resume handling skips recorded rows and rejects suite/configuration mismatches.

All **144 final answers were independently materialized and regraded in fresh scratch repositories**, agreeing with all saved frozen scores. Additional public-API behavioral probes ran symmetrically on every saved answer, including all five disagreement tasks and hard-tier passes. Final probe totals were Qwen 63/72 and Flash 68/72; every raw pass passed its focused probe. Each probe covers selected behavior, so its pass alone cannot override a frozen-check failure. The repository grader exposes one binary checker per task, so partial-check totals do not measure within-task partial correctness.

The paired comparison averages the three outputs within each task, then resamples **task IDs** with replacement: 20,000 bootstrap samples of 24 task IDs, random seed 20261012. Flash minus Qwen is +1.67 complete-task passes per run, with 95% interval **[-2.33, +5.67]**. Repeats stay clustered within tasks. The interval includes zero; the historical 27B advantage was not observed in the corrected mean, but these tasks do not resolve a reliable advantage beyond this suite.

Quantization, weight variants, engines, KV formats, context/speculation and GPU allocation differ. This measures the named local configurations on synthetic repository tasks, not hosted frontier parity or general model-only superiority. Request errors, missing final content and truncation are reported separately from solution failures.

## Audit revisions and version history

The raw campaign scores and frozen checker never changed. Early e1/e8 probes assumed behavior not required by the public contract; their revised records are explicitly labeled. Final e3/e20 probes initially supplied unsupported inputs (a transport integer instead of `(status, body)`, and a batch-only object instead of an iterable for `drain`). Those probes were corrected against the public API contracts, rerun symmetrically and preserved in superseding final records. `probes.v1.json` and early-probe versions retain the superseded evidence. No offline score correction was applied. A report-summary counting bug that selected Qwen rows using the shared `flash` filename prefix was also corrected; final lane membership uses exact campaign tags.

The copied scripts are documentation snapshots, not a relocated runnable installation: they refer to native model paths, engine builds and the original benchmark checkout. Reproduction should use `/home/USER/bench` and the archived frozen suite/configuration. Model weights and engine executables were not copied into the vault.

## Campaign outputs

| Campaign | Complete | Hard | Full result | Full answers/reasoning | Request log | Readiness | Server log |
|---|---:|---:|---|---|---|---|---|
| qwen27b / 40 | 21/24 | 12/14 | [JSON](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-40.json) | [Answers](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-40.answers.jsonl) | [Request log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-40.log) | [Readiness](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-40.readiness.json) | [Server log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-40.server.log) |
| flash / 40 | 23/24 | 13/14 | [JSON](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-40.json) | [Answers](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-40.answers.jsonl) | [Request log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-40.log) | [Readiness](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-40.readiness.json) | [Server log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-40.server.log) |
| flash / 41 | 22/24 | 12/14 | [JSON](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-41.json) | [Answers](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-41.answers.jsonl) | [Request log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-41.log) | [Readiness](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-41.readiness.json) | [Server log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-41.server.log) |
| qwen27b / 41 | 21/24 | 12/14 | [JSON](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-41.json) | [Answers](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-41.answers.jsonl) | [Request log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-41.log) | [Readiness](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-41.readiness.json) | [Server log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-41.server.log) |
| qwen27b / 42 | 21/24 | 12/14 | [JSON](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-42.json) | [Answers](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-42.answers.jsonl) | [Request log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-42.log) | [Readiness](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-42.readiness.json) | [Server log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-42.server.log) |
| flash / 42 | 23/24 | 13/14 | [JSON](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-42.json) | [Answers](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-42.answers.jsonl) | [Request log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-42.log) | [Readiness](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-42.readiness.json) | [Server log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-42.server.log) |

## Every archived supporting file

The original report is retained unchanged, and the vault findings note uses vault-relative links and embedded charts. [inventory.json](../assets/qwen27b-flash-matched-20261012-165802/inventory.json) records copied-file sizes, SHA-256 checksums and native source paths.

### Final report and charts

- [qwen27b-flash-matched-20261012-165802.chart-data.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.chart-data.json)
- [qwen27b-flash-matched-20261012-165802.deltas.png](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.deltas.png)
- [qwen27b-flash-matched-20261012-165802.deltas.svg](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.deltas.svg)
- [qwen27b-flash-matched-20261012-165802.report.md](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.report.md)
- [qwen27b-flash-matched-20261012-165802.tradeoff.png](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.tradeoff.png)
- [qwen27b-flash-matched-20261012-165802.tradeoff.svg](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.tradeoff.svg)

### Audit, suite, provenance, self-tests and historical context

- [matched-probe-selftest.json](../assets/qwen27b-flash-matched-20261012-165802/results/matched-probe-selftest.json)
- [matched-probe-selftest.log](../assets/qwen27b-flash-matched-20261012-165802/results/matched-probe-selftest.log)
- [oct1-dsw2-med.json](../assets/qwen27b-flash-matched-20261012-165802/results/oct1-dsw2-med.json)
- [qwen27b-flash-matched-20261012-165741.manifest.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165741.manifest.json)
- [qwen27b-flash-matched-20261012-165802-flash-metadata.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-metadata.json)
- [qwen27b-flash-matched-20261012-165802-flash-source.patch](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-source.patch)
- [qwen27b-flash-matched-20261012-165802-medium-template.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-medium-template.json)
- [qwen27b-flash-matched-20261012-165802-qwen-metadata.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen-metadata.json)
- [qwen27b-flash-matched-20261012-165802-qwen-props.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen-props.json)
- [qwen27b-flash-matched-20261012-165802-reasoning-verification.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-reasoning-verification.json)
- [qwen27b-flash-matched-20261012-165802.engine-metadata.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.engine-metadata.json)
- [qwen27b-flash-matched-20261012-165802.hardware.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.hardware.json)
- [qwen27b-flash-matched-20261012-165802.manifest.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.manifest.json)
- [qwen27b-flash-matched-20261012-165802.probes.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.probes.json)
- [qwen27b-flash-matched-20261012-165802.probes.v1.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.probes.v1.json)
- [qwen27b-flash-matched-20261012-165802.provenance.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.provenance.json)
- [qwen27b-flash-matched-20261012-165802.regrade.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.regrade.json)
- [qwen27b-flash-matched-20261012-165802.suite.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.suite.json)
- [qwen27b-flash-matched-20261012-165802.verification.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.verification.json)
- [qwen27b-flash-matched-launch-plan.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-launch-plan.json)
- [qwen27b-flash-matched-preflight-selftest.log](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-preflight-selftest.log)
- [qwen27b-flash-matched-strata-config.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-strata-config.json)
- [strata-20261011-deepswe2-r1.json](../assets/qwen27b-flash-matched-20261012-165802/results/strata-20261011-deepswe2-r1.json)
- [strata-20261011-deepswe2-r2.json](../assets/qwen27b-flash-matched-20261012-165802/results/strata-20261011-deepswe2-r2.json)
- [strata-20261012-contract-v2-frozen.json](../assets/qwen27b-flash-matched-20261012-165802/results/strata-20261012-contract-v2-frozen.json)
- [strata-20261012-contract-v2-selftests.json](../assets/qwen27b-flash-matched-20261012-165802/results/strata-20261012-contract-v2-selftests.json)

### Per-campaign supplemental audit records

- [qwen27b-flash-matched-20261012-165802-flash-40.audit.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-40.audit.json)
- [qwen27b-flash-matched-20261012-165802-flash-41.audit.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-41.audit.json)
- [qwen27b-flash-matched-20261012-165802-flash-42.process-tree.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-flash-42.process-tree.json)
- [qwen27b-flash-matched-20261012-165802-qwen27b-40.audit.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-40.audit.json)
- [qwen27b-flash-matched-20261012-165802-qwen27b-40.early-probes.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-40.early-probes.json)
- [qwen27b-flash-matched-20261012-165802-qwen27b-40.early-probes.v2.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-40.early-probes.v2.json)
- [qwen27b-flash-matched-20261012-165802-qwen27b-40.early-probes.v3.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802-qwen27b-40.early-probes.v3.json)

### Operational documentation and source snapshots

- [MATCHED_COMPARISON.md](../assets/qwen27b-flash-matched-20261012-165802/source/MATCHED_COMPARISON.md)
- [README.md](../assets/qwen27b-flash-matched-20261012-165802/source/README.md)
- [bench-run.py](../assets/qwen27b-flash-matched-20261012-165802/source/bench-run.py)
- [bench_lib.py](../assets/qwen27b-flash-matched-20261012-165802/source/bench_lib.py)
- [pack.json](../assets/qwen27b-flash-matched-20261012-165802/source/packs/deepswe2/pack.json)
- [selftest-deepswe2.py](../assets/qwen27b-flash-matched-20261012-165802/source/selftest-deepswe2.py)
- [targets.json](../assets/qwen27b-flash-matched-20261012-165802/source/targets.json)
- [bench_contract_v2.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/bench_contract_v2.py)
- [bench_corrected_suite.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/bench_corrected_suite.py)
- [corrected_code_refs.json](../assets/qwen27b-flash-matched-20261012-165802/source/tools/corrected_code_refs.json)
- [gguf_template.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/gguf_template.py)
- [matched_analysis.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/matched_analysis.py)
- [matched_charts.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/matched_charts.py)
- [matched_monitor.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/matched_monitor.py)
- [matched_probes.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/matched_probes.py)
- [run_matched_qwen_flash.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/run_matched_qwen_flash.py)
- [selftest_contract_v2.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/selftest_contract_v2.py)
- [selftest_corrected_suite.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/selftest_corrected_suite.py)
- [strata_corrected.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/strata_corrected.py)
- [strata_research_audit.py](../assets/qwen27b-flash-matched-20261012-165802/source/tools/strata_research_audit.py)



## Public snapshot — 2026-10-12

[Full-source RTX 3060 fork](https://github.com/AIMDaAlien/UnbiasedStrata-RTX3060) · [Dated release and patch](https://github.com/AIMDaAlien/UnbiasedStrata-RTX3060/releases/tag/rtx3060-2026-10-12). Exported documentation version: `rtx3060-2026-10-12`. On-demand, one-way export of the five selected project notes; originals and local evidence remain preserved. No automatic publishing or upstream tracking.
