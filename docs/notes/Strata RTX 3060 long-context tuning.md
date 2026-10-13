---
type: benchmark-report
topic: Strata long-context tuning
created: 2026-10-10
tags: [strata, benchmarks, optimization, rtx3060]
---
# Strata: faster long-context responses on the RTX 3060

The tuned setup takes **16.58% less time overall** on the tested long-context workloads. Fresh requests improved by **20–23%**, and growing conversations improved by **11–12%**. These settings are applied for the next launch. **AMD assistance stays off** because its follow-up test showed no benefit.

The model, output checks, context limit and power cap stayed the same. This is a scheduling and memory-use improvement on the existing IQ3_XXS model.

**Project overview:** [Strata RTX 3060 Optimization Showcase](Strata%20RTX%203060%20Optimization%20Showcase.md) — accepted result, paired confidence interval, visual evidence and the follow-up expert-kernel campaign.

![response-times](../assets/strata-prefill-20261010/response-times.png)

[Open the scalable chart](../assets/strata-prefill-20261010/response-times.svg) · [Chart data](../assets/strata-prefill-20261010/response-times.csv)

## What the chart measures

**Fresh request** means the model starts without a reusable conversation prefix. The clock runs until the complete answer arrives, including reading the prompt and generating the answer.

**Growing conversation** means a conversation expands in steps. Each checkpoint shows the total time spent on the conversation up to that point, including tool-call turns. It is cumulative, so it should be compared with the other bar in the same panel.

80K, 128K and 180K are input-token checkpoints: 80,000, 128,000 and 180,000 tokens. A token is a small piece of text. The configured context limit remains **196,608 tokens**.

## How much time it saves

| Workload | Input size | Original | Tuned | Time saved |
|---|---:|---:|---:|---:|
| Fresh response | 80K | 122.41 s | 94.30 s | 22.96% |
| Fresh response | 128K | 194.83 s | 153.89 s | 21.01% |
| Fresh response | 180K | 280.61 s | 223.61 s | 20.31% |
| Growing conversation | 80K | 172.03 s | 151.26 s | 12.07% |
| Growing conversation | 128K | 284.56 s | 252.09 s | 11.41% |
| Growing conversation | 180K | 419.82 s | 374.54 s | 10.79% |

For example, a fresh 180K request now finishes in about **3 minutes 44 seconds**, down from **4 minutes 41 seconds**. The growing conversation through 180K takes about **6 minutes 15 seconds**, down from **7 minutes**.

Times are averages across five repetitions. Percentages use the paired geometric mean, which combines proportional changes without letting the longest workload dominate. The overall 95% confidence interval corresponds to **16.53–16.63% less time**. It describes repeatability on this machine and these fixtures; other models and workloads may behave differently.

## What changed, in plain language

The main bottleneck was **prefill**: processing the input before the model starts answering. At 180K, even the tuned setup spends about 218 seconds on input processing and 5.7 seconds generating the answer.

Three controls worked together:

- **Fused prefill kernels** combine expert operations and reduce intermediate memory traffic. Fusion alone produced a modest improvement in screening.
- **A larger chunk ceiling** lets the model process more input at once, reducing repeated transfers of expert weights. An expert is one of the model's specialized blocks of weights.
- **A larger streaming ring** gives expert transfers more room to run ahead of GPU computation, reducing the time the GPU waits for weights.

Chunk and ring sizing provided most of the gain. The larger ring also uses GPU memory, so the final chunk is smaller than the ceiling: **10,496 tokens** on this machine. That tradeoff was faster in measured full responses.

Forced tile sizes of 64 and 128 showed no useful advantage over automatic sizing. Raising the chunk ceiling again to 32,768 did not justify a change. KV staging and answer generation were small shares of fresh-request time, so speculative changes there were deferred.

## The selected configuration

These controls are stored in `/home/USER/.config/unbiasedstrata/config.json` and reach the actual inference process:

```json
"environment": {
  "CUDA_VISIBLE_DEVICES": "0",
  "STRATA_RESIDENT_HEADROOM_GIB": "8",
  "OMP_NUM_THREADS": "1",
  "STRATA_PF_FUSED": "1",
  "STRATA_PREFILL_AUTO_MAX": "16384",
  "STRATA_PREFILL_RING": "512"
}
```

Tile sizing stays automatic. The setup keeps the **RTX 3060 at 100 W**, **56 GiB workload memory limit**, **swap disabled**, **12 CPU threads**, **int8 KV**, and a **32,768-token resident KV window**. The production service was left stopped after testing; the next launch uses the tuned configuration.

The engine also gained a conservative buffer guard for mixed expert-kernel fallback layers. The benchmark harness now records and checks environment variables and the executable hash, so an experiment cannot silently run with the wrong optimization settings.

## Why AMD remains disabled

After tuning NVIDIA, we tested AMD assistance for **decode only**. NVIDIA retained fused prefill and access to every expert needed for input processing. This avoided changing prefill ownership or removing its existing safety exclusion.

Both sides passed their quality checks, with **zero AMD helper fallback rows**. Nevertheless, the AMD-assisted setup took about **0.99% more time overall**, and all six workload buckets were slightly slower.

This was one feasibility pair, so it does not establish a statistically significant slowdown. It clearly failed the initial requirement for at least a **10% reduction in total time**. Five AMD acceptance pairs were therefore not warranted, and AMD stays off. An earlier full-prefill AMD screen was about 43% slower, so a new HIP prefill kernel and transfer pipeline are deferred too.

## How the result was checked

The accepted NVIDIA comparison used **five alternating pairs**: original then tuned, followed by tuned then original, and so on. Every profile used the same model, saved requests and quality fixtures. Each profile recorded 27 main-request turns, plus tool-call turns in the growing conversation.

All retrieval, generated-code, completion, token-count, tool-call, prefix-reuse and no-swap checks passed. Startup logs confirmed actual fused-kernel execution. The harness checked the live process environment, executable hash, GPU cap and memory settings. Seven harness unit checks also passed. Failed, incomplete, truncated or fallback runs cannot count as speed wins.

## Rollback and evidence

The original configuration is preserved at:

```text
/home/USER/.config/unbiasedstrata/config.json.before-prefill-20261011-010616
```

The original binary is preserved at:

```text
/home/USER/opt/UnbiasedStrata/build/unbiased-strata.before-prefill-tuning
```

With inference stopped, restoring both copies to their original paths returns the original setup. Source and benchmark artifacts remain available for review.

Small evidence files are stored with this note: [NVIDIA acceptance](../assets/strata-prefill-20261010/decision.json), [AMD feasibility](../assets/strata-prefill-20261010/amd-decision.json), and [application and rollback record](../assets/strata-prefill-20261010/application.json).

The complete measurements and research are on this machine under `/home/USER/opt/UnbiasedStrata/local/`: `PREFILL_RESULTS.md`, `PREFILL_RESEARCH.md`, and `benchmarks/prefill-20261010/`. The chart can be regenerated with `plot_prefill_results.py` from those paired measurements.

Related: [Strata Bench](Strata%20Bench.md) · Models & Serving · Benchmark Methodology

## Preliminary QSA screen — overnight October 10–11, 2026

**Preliminary: one screening pair; no confidence interval or validated gain.** The accepted 16.58% result above remains separate. Production configuration, binary and service settings were preserved; the service remains stopped.

The frozen control retained fused prefill, automatic tiles, chunk ceiling 16,384, ring 512, context 196,608, RTX 3060 at 100 W, 56 GiB memory limit, zero workload swap and AMD off. Treatment changed only `STRATA_TOPK_ACTIVE_ANY` from `0` to `1`. Diagnostic overrides were cleared.

Exact selected-ID parity passed all 104 cases in each configuration, covering both capacities (196,608 and 262,144), 80K/128K/180K, register boundaries, tied scores, partial blocks and absent/invalid bounds. IDs also matched between capacities. Actual engine dispatch was verified: control used the wide capacity path; treatment used active-bound registers below the CUDA cutoff and the wide fallback above it.

Screening decision: **rejected for rollout**. The six-bucket geometric-mean completed-response time changed by **0.112% less time**. The screen requires at least 2% less time and no bucket more than 5% slower; every quality check must pass. This result authorizes no production change.

| Workload | Input | Control | Treatment | Time saved |
|---|---:|---:|---:|---:|
| Fresh | 80K | 94.43 s | 94.27 s | 0.18% |
| Fresh | 128K | 154.05 s | 153.82 s | 0.14% |
| Fresh | 180K | 223.88 s | 223.62 s | 0.12% |
| Growing | 80K | 151.51 s | 151.31 s | 0.13% |
| Growing | 128K | 252.46 s | 252.08 s | 0.15% |
| Growing | 180K | 374.68 s | 374.83 s | -0.04% |

Fresh timing runs through the complete response. Growing timing is cumulative through each checkpoint, including every intermediate turn and tool call. Both configurations completed all 27 main turns and all growing tool turns with quality, retrieval, code, completion, prefix reuse and no-swap checks passing.

### Instrumented profiles

These component measurements are separate from the uninstrumented screening pair. Selection includes scoring and top-k. Fused expert compute includes gate/up and down.

| Configuration / request | Prefill | Decode | Total response |
|---|---:|---:|---:|
| Control 128K | 150.206 s | 3.354 s | 153.691 s |
| Control 180K | 217.590 s | 5.889 s | 223.665 s |
| Treatment 128K | 150.472 s | 3.365 s | 153.971 s |
| Treatment 180K | 217.888 s | 5.899 s | 223.975 s |

| Configuration / request | QSA selection (% of prefill) | Attention | Expert compute | KV staging |
|---|---:|---:|---:|---:|
| Control 128K | 11.262 s (7.498%) | 13.963 s | 35.364 s | 6.771 s |
| Control 180K | 22.339 s (10.267%) | 19.882 s | 49.838 s | 10.088 s |
| Treatment 128K | 11.119 s (7.389%) | 13.995 s | 35.464 s | 6.779 s |
| Treatment 180K | 22.232 s (10.203%) | 19.924 s | 49.938 s | 10.076 s |

### Morning handoff

The active-bound setting is rejected for rollout (or remains incomplete if no decision exists). Five acceptance pairs are not warranted for a rejected setting. Wait for **continue** before further investigation. Use the frozen control (`STRATA_TOPK_ACTIVE_ANY=0`) as the baseline for any morning port assessment.

Residual treatment selection remains above 5% of prefill, so a targeted [streaming top-k port assessment](https://github.com/Niko1221/Strata/pull/743) is eligible for morning investigation after **continue**. No port was implemented tonight. Require exact selected-ID parity before timing any port.

Evidence directory: `/home/USER/opt/UnbiasedStrata/local/benchmarks/qsa-20261011-screen`. The archived manifest records frozen profiles, effective environment, all 51 fixture hashes and executable hashes; raw logs and exact selected-ID artifacts remain there. Final reporting-source hashes and correction notes are retained.

[Screen decision](../assets/strata-qsa-20261011-screen/decision.json) · [Instrumented profiles](../assets/strata-qsa-20261011-screen/profile-summary.json) · [Parity](../assets/strata-qsa-20261011-screen/parity.json) · [Morning handoff](../assets/strata-qsa-20261011-screen/MORNING_HANDOFF.md)


## QSA morning follow-up — October 11, 2026

After **continue**, the targeted [streaming top-k PR 743](https://github.com/Niko1221/Strata/pull/743) was assessed against the frozen control. **This port assessment is closed: the proposed coalesced radix selection is already implemented by the control's wide top-k kernel.** At context capacity 196,608, the RTX 3060 control uses a score-row stride of 49,154 blocks, above the register cutoff of 33,792; overnight dispatch logs confirm the wide path. Short early prompt chunks retain the existing reference path.

The PR and current wide kernel share coalesced radix reads, weighted thresholds, partial-block handling and lowest-index tie selection. Their emission implementations differ: the PR scans each chunk across the full thread block; the current wide kernel emits using warp-local scans. They are not identical source. Upstream closed the PR after adopting the wide path, and its author reported that the original large-context improvement was already covered by that path. No duplicate kernel was added and no new parity or speed result is claimed. Overnight exact selected-ID parity remains the evidence for the existing paths.

The QSA-selection profile combines scoring and top-k, so the remaining 7.50% / 10.27% of control prefill cannot be attributed to top-k alone. The **largest measured phase is fused expert compute**, including gate/up and down:

| Frozen control | Expert compute | Share of prefill |
|---|---:|---:|
| Fresh 128K | 35.364 s | 23.54% |
| Fresh 180K | 49.838 s | 22.90% |

The active-bound setting remains rejected for rollout; no five-pair acceptance run is warranted for it. Production configuration, binary and service settings are unchanged; the service remains stopped. An unrelated `llama-server` was using the GPU during this read-only assessment and was left running. No build or GPU benchmark was started. Expert-kernel development, KV overlap and GDN changes remain outside this task's scope; those need a separately authorized task. The targeted QSA branch ends here.

The overnight hibernation request returned success, as recorded in the saved quiet-night evidence. No further sleep or wake was requested during this follow-up.

[Port assessment](../assets/strata-qsa-20261011-stream-assessment/ASSESSMENT.md) · [Follow-up handoff](../assets/strata-qsa-20261011-stream-assessment/HANDOFF.md) · [Evidence manifest](../assets/strata-qsa-20261011-stream-assessment/manifest.json)


## Native fused expert campaign — October 11, 2026

This is a separate result from the accepted **16.58%** prefill tuning and the rejected QSA screen above. The bounded native-expert campaign is complete and **did not meet the required 5% reduction in total response time**. Production remains unchanged and stopped; variant 0 remains the default.

The 256-thread/four-stage, 256-thread/three-stage, farther-prefetch and larger-grid experiments passed exact expert parity and required sanitizer checks. A frozen mode 5 table kept only four qualifying low-row cells: IQ2_XXS, IQ3_XXS and IQ3_S gate/up use mode 1; IQ4_NL down uses mode 2. Every other format/phase/row class retains control. Its new independent microbenchmark showed approximately 1.47% less combined expert time across sampled cases; this is not a total-response gain.

New final instrumented comparisons used the same frozen executable and unchanged fixtures/configuration. All fresh retrieval, code, completion, token-count, fresh-state and no-swap checks passed, with identical generated token counts.

| Fresh request | Control | Mode 5 | Candidate/control |
|---|---:|---:|---:|
| 128K | 154.857 s | 155.045 s | 1.001219 |
| 180K | 225.027 s | 225.431 s | 1.001797 |

Mode 5 was about 0.12% and 0.18% slower in these profiling-gate observations. The required 0.95 ratio at both lengths failed, so no uninstrumented six-bucket screening or five-pair acceptance was warranted. No accepted speedup or confidence interval is claimed.

Earlier disconnected-era measurements were used only for candidate selection; failed, incomplete, empty and foreign-GPU attempts remain excluded. Final mode 5 checks and response profiles recorded timestamps/boot IDs and passed source, binary, fixture, model-file, configuration and clock-continuity checks with exclusive GPU ownership at 100 W. No samples were dropped for being unusually fast or slow.

Smaller blocks did not reliably deliver two-block residency: IQ2_XS/IQ2_S gate/up used 160/158 registers per thread, and reduced shared memory did not remove that register limit. Most long-prefill work stayed in the high-row control class; selected gains were confined to short tail chunks. QSA remained closed. No precision reduction, register cap, split-K, decoded model cache, expert-transfer change or upstream update was introduced.

The experiment is retained for review, defaults to control and has an isolated rollback patch preserving the pre-existing dirty tree. Optional workloads remain stopped; restoration commands are saved. No rollout, wake, hibernation or further test is scheduled. Exact next action: review the retained evidence if useful; this campaign is closed at its profiling gate.

[Campaign report](../assets/strata-expert-20261011T161207Z/REPORT.md) · [Handoff](../assets/strata-expert-20261011T161207Z/HANDOFF.md) · [Final response gate](../assets/strata-expert-20261011T161207Z/profile-gate.json) · [Correctness](../assets/strata-expert-20261011T161207Z/correctness-summary.json) · [Frozen dispatch](../assets/strata-expert-20261011T161207Z/winning-dispatch.json) · [Review/rollback patch](../assets/strata-expert-20261011T161207Z/campaign-only.patch)

Full evidence: `/home/USER/opt/UnbiasedStrata/local/benchmarks/expert-20261011T161207Z`.


## Public snapshot — 2026-10-12

[Full-source RTX 3060 fork](https://github.com/AIMDaAlien/UnbiasedStrata-RTX3060) · [Dated release and patch](https://github.com/AIMDaAlien/UnbiasedStrata-RTX3060/releases/tag/rtx3060-2026-10-12). Exported documentation version: `rtx3060-2026-10-12`. On-demand, one-way export of the five selected project notes; originals and local evidence remain preserved. No automatic publishing or upstream tracking.
