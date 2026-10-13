---
type: benchmark-log
topic: Strata Bench
---
# Strata Bench

> **Featured project:** [Strata RTX 3060 Optimization Showcase](Strata%20RTX%203060%20Optimization%20Showcase.md) — accepted **16.58% less response time** across six long-context workloads, with the confidence interval, evidence figures and rejected expert-kernel follow-up.


## 2026-10-12 — Corrected matched DeepSWE2 comparison

[2026-10-12 Matched Qwen 27B vs Flash DeepSWE2](2026-10-12%20Matched%20Qwen%2027B%20vs%20Flash%20DeepSWE2.md) — six complete campaigns, 144 audited results over 24 distinct synthetic repository tasks. Flash averaged **22.67/24** versus Qwen **21.00/24**; the task-bootstrap interval for the +1.67 Flash delta is **[-2.33, +5.67]**, including zero. The historical 27B advantage was not observed on this corrected suite. The note embeds delta and capability/latency charts, with [full methods, provenance and all archived supporting files](2026-10-12%20Matched%20Qwen%20vs%20Flash%20%E2%80%94%20Methods%20and%20artifacts.md).


## 2026-10-05 17:37
**Done:** Compiled the Strata vs llama.cpp wallclock comparison for Qwen3.8-Flash-Next IQ3_XXS from the 2026-09-29 swe40 runs.
**Findings:** Same 40-task suite @3072 budget: Strata (rig, dual 3060) 732.2s / 97/112 / ~48 t/s vs llama.cpp (Unraid) 2055.0s / 99/112 / ~17 t/s — Strata ~2.8x faster wall, quality a wash. Not a pure engine A/B (different hosts); part of the win is Strata's expert cache (40-83% hit). Strata TTFT: 29s warm at 40K prompt, ~19s at 8K.
**Recommendations:** For a clean engine delta, rerun llama.cpp swe40 on the rig with the same IQ3_XXS pack.


## 2026-10-10 — RTX 3060 long-context tuning

[Strata RTX 3060 Optimization Showcase](Strata%20RTX%203060%20Optimization%20Showcase.md) is the project hub for the accepted result, evidence figures and later expert-kernel campaign. [Strata RTX 3060 long-context tuning](Strata%20RTX%203060%20long-context%20tuning.md) retains the detailed applied profile, verification and rollback. Five alternating pairs found **16.58% less time overall** at 100 W: fresh requests improved 20–23%, growing conversations 11–12%. All quality checks passed. AMD decode-only missed the 10% improvement gate and remains disabled.
