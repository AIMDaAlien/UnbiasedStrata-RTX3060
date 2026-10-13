---
type: benchmark-run
category: Benchmarks
date: 2026-10-12
updated: 2026-10-12
suite: contract-v2
distinct_tasks: 24
runs_per_model: 3
recorded_results: 144
tags: [benchmark, qwen, flash, strata, deepswe2, local-inference]
---

# 2026-10-12 Matched Qwen 27B vs Flash DeepSWE2

**Hub:** Model Benchmarks · **Methods and complete artifact index:** [2026-10-12 Matched Qwen vs Flash — Methods and artifacts](2026-10-12%20Matched%20Qwen%20vs%20Flash%20%E2%80%94%20Methods%20and%20artifacts.md) · **Related:** [Strata Bench](Strata%20Bench.md) · Benchmark Methodology

Flash averaged 22.67/24 complete-task passes versus Qwen's 21.00/24. The historical 27B advantage was not observed in the corrected comparison. The paired task-bootstrap 95% interval for Flash minus Qwen is [-2.33, +5.67] passes; it includes zero.

Three repeats per model, paired seeds 40–42; 24 distinct synthetic repository tasks. Frozen contract-v2, source included, hidden checks excluded, medium reasoning, temperature zero, matched budgets and escalation. Request latency includes all escalation attempts; length finishes count every attempt, including escalated ones. Repository grading exposes one binary checker per task, so partial-check totals have no within-task resolution.

| Model / seed | Complete | Hard | Partial checks | Request errors | Empty finals | Length finishes | Median seconds | Median tokens/s | Runtime seconds |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen27b / 40 | 21/24 | 12/14 | 21/24 | 0 | 0 | 0 | 81.2 | 28.9 | 2173.9 |
| flash / 40 | 23/24 | 13/14 | 23/24 | 0 | 0 | 0 | 68.4 | 42.7 | 1837.4 |
| flash / 41 | 22/24 | 12/14 | 22/24 | 0 | 0 | 0 | 67.3 | 42.7 | 1925.4 |
| qwen27b / 41 | 21/24 | 12/14 | 21/24 | 0 | 0 | 0 | 80.8 | 29.1 | 2161.5 |
| qwen27b / 42 | 21/24 | 12/14 | 21/24 | 0 | 0 | 0 | 81.2 | 28.9 | 2172.4 |
| flash / 42 | 23/24 | 13/14 | 23/24 | 0 | 0 | 0 | 66.3 | 42.5 | 1905.8 |

Local configurations:

- Qwen: Swift Qwen3.8 27B Q5_K_M, llama.cpp build 10809, RX 9060 XT plus RTX 3060, context 131,072, q4_0 KV, MTP n=2.
- Flash: Qwen3.8-Flash-Next GSQ-RCO IQ3_XXS, UnbiasedStrata, RTX 3060 plus CPU with 12 threads, context 196,608, int8 KV with a 32,768-token resident window, speculation 4. Actual executable hashes and arguments are retained in the manifest.

Historical context: [oct1-dsw2-med.json](../assets/qwen27b-flash-matched-20261012-165802/results/oct1-dsw2-med.json) recorded Qwen 7/24 versus Flash 5/24 on the legacy suite. The later Strata legacy repeats scored 5/24 and 7/24. These are background results, not pooled into the corrected matched comparison.

Mean paired advantage (Flash minus Qwen): 1.67 complete tasks per run; task-ID bootstrap 95% interval [-2.33, 5.67]. Repeats are clustered within tasks, not treated as independent problems.

The historical 27B advantage does not survive in the observed mean on this corrected suite. The task-level interval includes zero, so these 24 tasks do not resolve a reliable advantage.

qwen27b: pooled median request latency 80.9s; pooled median decode 28.9 tokens/s; total scored-campaign runtime 108.5 minutes.
qwen27b: mean hard-tier passes 12.00/14.
qwen27b: mean 21.00/24; 21 tasks pass all repeats, 3 fail all repeats, 0 vary.
flash: pooled median request latency 66.6s; pooled median decode 42.5 tokens/s; total scored-campaign runtime 94.5 minutes.
flash: mean hard-tier passes 12.67/14.
flash: mean 22.67/24; 22 tasks pass all repeats, 1 fail all repeats, 1 vary.

Paired outcomes by seed:

- 40: Qwen wins 1, Flash wins 3, ties 20.
- 41: Qwen wins 2, Flash wins 3, ties 19.
- 42: Qwen wins 1, Flash wins 3, ties 20.

Paired seeds 40, 41 and 42 were sent and recorded for every scored request. At temperature zero the Strata frontend selects greedy decoding and does not forward a random seed to the engine; repeat differences should not be described as seed-driven sampling variance.

Tasks with a paired disagreement: e10-csv-dialect, e11-scheduler-priority, e2-lru-eviction, e24-fsm-parallel, e8-event-sourcing. All are included in both regrading and the focused probe audit.

Exact fixtures and executed checker code: [qwen27b-flash-matched-20261012-165802.suite.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.suite.json). Engine/source provenance and hardware metadata are retained beside the raw campaign files.

All 144 final answers were independently materialized and regraded in fresh scratch repositories. Full responses and every escalation attempt remain in campaign artifacts. Focused behavioral audit is recorded separately.

This compares local configurations. Q5_K_M versus IQ3_XXS quantization, llama.cpp versus Strata, differing context/KV/speculation and GPU allocation confound capability and speed. It cannot establish hosted frontier parity or performance beyond these 24 tasks. No best-of-three score is used.

Manifest: [qwen27b-flash-matched-20261012-165802.manifest.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.manifest.json); independent grading: [qwen27b-flash-matched-20261012-165802.regrade.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.regrade.json).

Focused public-API probes ran symmetrically on all 144 saved solutions. Each probe covers selected behavior, so passing it does not override a failure in the full checker. Their results are separate from raw grading:
[qwen27b-flash-matched-20261012-165802.probes.json](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.probes.json).

| Disagreement task | Qwen seeds 40/41/42 | Flash seeds 40/41/42 | Recorded failure evidence |
|---|---|---|---|
| e10-csv-dialect | F/F/F | P/P/P | check-fail: ValueError: I/O operation on closed file. |
| e11-scheduler-priority | F/F/F | P/P/P | check-fail: AssertionError: [{'ok': True, 'result': 4}, {'ok': True, 'result': 6}, {'ok': True, 'result': 10}, {'ok': True, 'result': 8}] |
| e2-lru-eviction | F/F/F | P/P/P | check-fail: SyntaxError: invalid syntax |
| e24-fsm-parallel | P/P/P | F/F/F | check-fail: AssertionError: history must be a copy |
| e8-event-sourcing | P/P/P | P/F/P | check-fail: evt.aggregate.InvalidEvent: missing seq |

- qwen27b: 24/24 tasks have byte-identical final answers across all three repeats.
- qwen27b: 63/72 probe passes; 0 raw passes fail the additional probe.
- flash: 1/24 tasks have byte-identical final answers across all three repeats.
- flash: 68/72 probe passes; 0 raw passes fail the additional probe.

Audit probe revisions: early e1/e8 assumptions and final e3/e20 input assumptions were corrected to match the public API contracts. Superseded probe records are retained; the frozen suite and raw campaign scores were unchanged. No offline score correction was applied.

![qwen27b-flash-matched-20261012-165802.deltas](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.deltas.png)

[Delta chart SVG](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.deltas.svg) · [Chart data](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.chart-data.json)

![qwen27b-flash-matched-20261012-165802.tradeoff](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.tradeoff.png)

[Trade-off chart SVG](../assets/qwen27b-flash-matched-20261012-165802/results/qwen27b-flash-matched-20261012-165802.tradeoff.svg)

Completion verified: six campaigns with 24 unique rows each; identical task/message/check fingerprints; 144/144 independent regrades agree. All requests returned final content without errors or truncation. Benchmark servers are stopped and Ornith is inactive. Controller wall time was 208.2 minutes, including launch/readiness, cleanup and the initial audit/chart generation.


## Public snapshot — 2026-10-12

[Full-source RTX 3060 fork](https://github.com/AIMDaAlien/UnbiasedStrata-RTX3060) · [Dated release and patch](https://github.com/AIMDaAlien/UnbiasedStrata-RTX3060/releases/tag/rtx3060-2026-10-12). Exported documentation version: `rtx3060-2026-10-12`. On-demand, one-way export of the five selected project notes; originals and local evidence remain preserved. No automatic publishing or upstream tracking.
