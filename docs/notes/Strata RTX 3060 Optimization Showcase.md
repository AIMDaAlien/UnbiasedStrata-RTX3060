---
type: project-showcase
topic: Strata RTX 3060 optimization
created: 2026-10-11
tags: [strata, benchmarks, optimization, rtx3060, showcase]
---
# Strata on the RTX 3060: optimization showcase

**A validated 16.58% reduction in total response time** on the tested long-context workloads, with quality checks intact and the GPU held at 100 W. The result came from a combined prefill configuration; the measurements do not claim separate gains for each setting.

![accepted-response-times](../assets/strata-rtx3060-showcase/accepted-response-times.png)

[Open the scalable chart](../assets/strata-rtx3060-showcase/accepted-response-times.svg) · [Download chart data](../assets/strata-rtx3060-showcase/accepted-response-times.csv)

## Result at a glance

| Evidence | Result | Status |
|---|---|---|
| Six fresh and growing long-context buckets | **16.58% less time overall**; every bucket improved | Accepted after five alternating pairs |
| Paired 95% interval for candidate/original response time | **0.83366–0.83473**, equivalent to about 16.53–16.63% less time | Accepted result |
| Native fused-expert kernel samples | **1.47% lower sampled kernel time** | Microbenchmark only |
| Native fused-expert profiled responses | **0.12% slower at 128K; 0.18% slower at 180K** | Failed the 5% response-time gate |

The accepted measurements used the same model, saved fixtures, context and 100 W cap. Fresh requests improved 20–23%; cumulative growing conversations improved 11–12%. The growing checkpoints include intermediate turns and tool calls. Quality, retrieval, code, completion, token-count, prefix reuse, tool-call and no-swap checks passed. The confidence interval describes repeatability on these fixtures and this machine.

## What changed

The selected NVIDIA profile combines **fused prefill**, an automatic prefill chunk ceiling of **16,384 tokens**, and a **512-slot streaming ring**. The larger chunk ceiling reduces repeated expert-weight transfers; the larger ring gives transfers more room to run ahead of GPU computation. The accepted comparison evaluated the profile as a bundle, so it does not support assigning an individual percentage to any one setting.

Tile sizing stayed automatic. The run kept the RTX 3060 at 100 W, the 56 GiB memory limit, swap disabled, int8 KV and the existing model. Startup evidence confirmed the fused kernels and a resolved chunk size of 10,496 tokens on this machine. AMD assistance stayed off after its separate feasibility comparison failed its improvement threshold.

## Engineering and evidence

- The tuning note records the selected settings, application and rollback details: [Strata RTX 3060 long-context tuning](Strata%20RTX%203060%20long-context%20tuning.md).
- Five alternating acceptance pairs were checked with unchanged fixtures and quality gates. The saved acceptance decision and raw paired timings are linked from the tuning note.
- The harness recorded the effective environment and executable identity; startup logs verified the actual fused-kernel path.
- A conservative buffer guard was added around mixed expert-kernel fallback layers. Benchmark instrumentation records the effective settings and executable hash so a run cannot silently use the wrong configuration.
- The expert-kernel campaign exercised exact parity and required CUDA sanitizers. Its final response profiles failed the explicit gate, so it produced no accepted end-to-end speedup claim.

## Where time goes

![prefill-bottleneck](../assets/strata-rtx3060-showcase/prefill-bottleneck.png)

[Scalable bottleneck chart](../assets/strata-rtx3060-showcase/prefill-bottleneck.svg) · [Component data](../assets/strata-rtx3060-showcase/prefill-bottleneck.csv)

This diagnostic uses the frozen control’s profiled fresh requests. Expert GEMM gate/up is the largest reported phase. The GDN group sums its three detailed components—convolution and gates, recurrence, and output projection—and omits the overlapping aggregate GDN timer. These profiles guide investigation; they are separate from the accepted uninstrumented response-time measurements.

## Expert campaign: useful kernel signal, failed response gate

![expert-campaign-gate](../assets/strata-rtx3060-showcase/expert-campaign-gate.png)

[Scalable expert-campaign chart](../assets/strata-rtx3060-showcase/expert-campaign-gate.svg) · [Profile and microbenchmark data](../assets/strata-rtx3060-showcase/expert-campaign-gate.csv)

The independent mode 5 microbenchmark measured a 1.47% reduction in sampled combined expert-kernel time. The two final instrumented fresh responses were 0.12% and 0.18% slower than control, missing the required 5% improvement at both lengths. These instrumented observations are profiling evidence, not acceptance statistics. The campaign stopped at this gate; no six-bucket screening or five-pair acceptance run followed.

## Lessons and parked roadmap

- Measure full response time: a kernel-only gain does not establish an end-to-end speedup.
- Preserve measurement classes: accepted uninstrumented pairs, profiling observations and microbenchmarks answer different questions.
- Keep optimization attribution conservative when settings were accepted as a bundle.
- **Parked, untested:** GDN kernel optimization, KV staging/overlap, and further QSA/attention work. Existing evidence does not justify a rollout; any future investigation needs its own scoped measurement and acceptance gate.

## Source notes and reports

- Accepted tuning details: [Strata RTX 3060 long-context tuning](Strata%20RTX%203060%20long-context%20tuning.md)
- [Accepted decision](../assets/strata-prefill-20261010/decision.json) · [Original six-bucket source data](../assets/strata-prefill-20261010/response-times.csv)
- Benchmark history: [Strata Bench](Strata%20Bench.md)
- Expert campaign report: [REPORT.md](../assets/strata-expert-20261011T161207Z/REPORT.md) · [Independent microbenchmark report](../assets/strata-expert-20261011T161207Z/mode5-independent-report.json) · [Final response gate](../assets/strata-expert-20261011T161207Z/profile-gate.json) · [Final profiles](../assets/strata-expert-20261011T161207Z/final-profile-summary.json)
- Benchmark index: Model Benchmarks


## Public snapshot — 2026-10-12

[Full-source RTX 3060 fork](https://github.com/AIMDaAlien/UnbiasedStrata-RTX3060) · [Dated release and patch](https://github.com/AIMDaAlien/UnbiasedStrata-RTX3060/releases/tag/rtx3060-2026-10-12). Exported documentation version: `rtx3060-2026-10-12`. On-demand, one-way export of the five selected project notes; originals and local evidence remain preserved. No automatic publishing or upstream tracking.
