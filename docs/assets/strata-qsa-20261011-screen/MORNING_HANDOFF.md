# Morning handoff — preliminary QSA screen

Decision: **rejected for rollout**. One pair improved geometric-mean response time by 0.1124%; the required gate is 2%. No confidence interval or validated gain.

Exact parity: 104 cases per setting, both capacities; selected IDs identical. All four profiles passed. The paired runs passed all 54 main requests and 48 tool calls, including intermediate growing checks. Production configuration, binary and service are unchanged; service stopped.

| Workload | Input | Control | Treatment | Time saved |
|---|---:|---:|---:|---:|
| Fresh | 80K | 94.43 s | 94.27 s | 0.18% |
| Fresh | 128K | 154.05 s | 153.82 s | 0.14% |
| Fresh | 180K | 223.88 s | 223.62 s | 0.12% |
| Growing | 80K | 151.51 s | 151.31 s | 0.13% |
| Growing | 128K | 252.46 s | 252.08 s | 0.15% |
| Growing | 180K | 374.68 s | 374.83 s | -0.04% |

Growing times are cumulative and include tool turns. Exclusions: none.

Residual treatment QSA selection: **7.389% at 128K; 10.203% at 180K** of profiled prefill. Full component timings are in [profiles](profile-summary.json).

Exact next step: wait for **continue**, then assess [streaming top-k PR 743](https://github.com/Niko1221/Strata/pull/743) against the frozen control (`control.json`, active-bound flag 0). Require exact selected-ID parity before timing. The rejected active-bound setting does not warrant five acceptance pairs.

Both RAM devices and the motherboard are verified Off through OpenRGB. Benchmark and RGB helper processes are stopped. Hibernation is next, with existing deep suspend as fallback; the actual request outcome is saved in [quiet-night.json](quiet-night.json). No wake or test timer was scheduled; no fan or boot settings changed.

Evidence and resume state: `/home/USER/opt/UnbiasedStrata/local/benchmarks/qsa-20261011-screen`. [Decision](decision.json), [state](state.json), [manifest and hashes](manifest.json), [main review](main-review.json).
