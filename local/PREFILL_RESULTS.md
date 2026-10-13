# Measured RTX 3060 prefill tuning

Five alternating paired repetitions used unchanged IQ3_XXS fixtures at 80K, 128K and 180K, with context 196,608, RTX 3060 capped at 100 W, MemoryMax 56 GiB and swap disabled. Fresh requests use completed-response wall time; growing checkpoints use cumulative conversation wall time, including tool turns.

The geometric-mean time reduction was **16.58%**. The paired 95% confidence interval for candidate/baseline time was [0.83366, 0.83473]. All six buckets improved and every quality, retrieval, code, completion, prefix-reuse, tool-call and no-swap check passed, including intermediate growing turns.

| Workload | Context | Baseline seconds | Tuned seconds | Time saved |
|---|---:|---:|---:|---:|
| fresh | 80,000 | 122.41 | 94.30 | 22.96% |
| fresh | 128,000 | 194.83 | 153.89 | 21.01% |
| fresh | 180,000 | 280.61 | 223.61 | 20.31% |
| growing | 80,000 | 172.03 | 151.26 | 12.07% |
| growing | 128,000 | 284.56 | 252.09 | 11.41% |
| growing | 180,000 | 419.82 | 374.54 | 10.79% |

Mean fresh-request diagnostics for the tuned candidate were: 80K TTFT 89.59 s / prefill 89.46 s / decode 4.75 s; 128K 150.71 s / 150.55 s / 3.21 s; 180K 217.97 s / 217.76 s / 5.67 s. These are diagnostics; acceptance uses the complete wall-time measurements above.

The winning controls are `STRATA_PF_FUSED=1`, `STRATA_PREFILL_AUTO_MAX=16384`, and `STRATA_PREFILL_RING=512`. Tile sizing remains automatic. Startup logs verify fused kernels and a resolved chunk of 10,496 with 2,694 borrowed expert-cache slots (4.39 GiB). The pinned CPU expert complement is 39.16 GiB. Profile environment variables are forwarded and checked in the live process; each run records the actual executable hash and GPU power limit.

The source also conservatively retains full MoE buffers for mixed MMQ/FP16 fallback layers ([upstream issue 954](https://github.com/Niko1221/Strata/issues/954)). This guard is included in both sides of every acceptance pair.

The main gain came from chunk/ring sizing, which reduced copy stalls; fusion alone was only a modest screen improvement. Forced 64/128 tiles and the higher 32,768 ceiling did not justify overriding the selected values. KV staging and fresh decode were small shares of total time, so no speculative KV-prefetch or MTP change was introduced.

Evidence: [decision](benchmarks/prefill-20261010/decision.json), [paired runs](benchmarks/prefill-20261010/paired), [research and screens](PREFILL_RESEARCH.md). Seven harness unit checks passed. All ten acceptance profiles match executable SHA-256 `9e7e8c27be4218bebda4035a5ed588ed9b325dd5857c55e7d6059ea92eb01764`.

These confidence bounds describe repeated measurements on this machine and these fixtures; they do not establish gains for other models or hardware.

Applied the winning NVIDIA profile to `/home/USER/.config/unbiasedstrata/config.json`. AMD remains disabled after its completed decode-only feasibility comparison. Production was inactive and has not been started. Configuration rollback: `/home/USER/.config/unbiasedstrata/config.json.before-prefill-20261011-010616`. Binary rollback: `build/unbiased-strata.before-prefill-tuning`. Restore both for the original setup; the new binary is shared by every acceptance pair.

## AMD decision

A fresh comparison against the tuned NVIDIA configuration preserved NVIDIA fused prefill and gave AMD only disjoint decode expert work. Both profiles passed all 27 turns, including helper health and zero fallback rows. The one-pair geometric-mean AMD/off time ratio was **1.00986** (about 0.99% slower). Every bucket was slightly slower: fresh 80K/128K/180K ratios 1.01063/1.00263/1.00219; growing ratios 1.01368/1.01617/1.01398. This is a feasibility screen, not a statistically established regression. It does not justify the five paired repetitions required for enablement, because it misses the initial 10% improvement gate.

Across the six decision buckets, mean reported prefill/decode times were 81.26/4.18 s without AMD and 81.44/4.41 s with AMD. Both profiles had a 56 GiB cgroup peak and no swap. Across 27 main-request diagnostics, the helper averaged 6.78 ms host transfer accounting, 309.94 ms wait, 147.90 ms device transfer and 244.44 ms compute. These overlap and must not be added. All helper fallback rows were zero. [AMD decision and profiles](benchmarks/prefill-20261010/amd-decision.json).

The earlier full-prefill AMD screen was 43.2% slower. With neither AMD path showing a gain, a new bounded HIP prefill kernel and transfer pipeline are deferred. Production remains NVIDIA-only; no new persistent service was started.
