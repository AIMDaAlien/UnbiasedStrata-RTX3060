# Native fused experts: RTX 3060 campaign

The bounded campaign is complete. **The candidate did not meet the required 5% reduction in total response time.** Production configuration, executable and launcher are unchanged; production remains stopped. Mode 0 remains the default.

## Fresh final response gate

These new instrumented requests used the same frozen executable, identical canonical fixtures and frozen settings. All retrieval, code, completion, prompt-token-count, fresh-state and no-swap checks passed. Generated token counts were identical (128 at 128K, 256 at 180K).

| Fresh request | Control mode 0 | Candidate mode 5 | Candidate/control |
|---|---:|---:|---:|
| 128K | 154.857 s | 155.045 s | 1.001219 |
| 180K | 225.027 s | 225.431 s | 1.001797 |

Both ratios exceeded 0.95. Mode 5 was approximately 0.12% and 0.18% slower in these profiled requests. These are profiling-gate observations, not accepted speed results. No uninstrumented six-bucket screening pair or five-pair acceptance was run; confidence intervals and growing/tool/prefix checks for this candidate were not claimed. The explicit gate required stopping here.

## Implementation and correctness

The original control dispatch and arithmetic remain available. Experimental modes 1/2 use 256 threads with four/three activation stages. Modes 3/4 test farther gate/up L2 prefetch and twice the persistent grid on the best preceding layout; ties within 1% selected the original control layout as their base. Native variants apply only to SM86 and unavailable or unmeasured specializations retain control. Original public interfaces, quantization, buffers, grouping and ring ownership are preserved.

Each mode, including mode 5, passed 266 exact-parity cases. The harness uses real two-byte-aligned packed expert weights, all ten actual format pairs, samples from all 48 layers, both tile shapes, edge/skew/uniform/empty row counts, zero and seeded finite activations, repeated tokens, nonzero batch starts, batch sizes 1/17/127/128, and successive batches across all 512 experts. It compares defined hidden codes/scales, FP32 down outputs and restored slot outputs bit for bit, with output sentinels and buffer guards. All required memcheck, racecheck and synccheck checks passed. Memcheck covers all ten pairs; compact race/sync cases cover both projections/tile shapes and the relevant pipelines. The interrupted broad racecheck is excluded.

Opt-in diagnostics separate gate/up plus epilogue from down, record resources and routing distributions on the existing compute stream, and collect after existing synchronization. No per-batch synchronization is added. With diagnostics disabled, no profiling events or records are allocated.

## Measurements and diagnosis

All valid mode 1–4 microbenchmarks contain 600 timing records each: ten warmups and five alternating pairs of twenty iterations per phase/format-pair/observed row class. The classes <=56 and >112 were observed; 57–112 remains control. Historical runs guide selection only because of the reported disconnections and missing early per-sample timestamps.

| Experimental mode | Combined expert-time ratio |
|---|---:|
| 1 | 1.001764 |
| 2 | 0.992156 |
| 3 | 1.019856 |
| 4 | 1.022413 |

The independently verified mode 5 achieved a sampled combined expert-time ratio of 0.985313 (about 1.47% lower), using new timestamps, per-measurement GPU ownership/power checks, continuous ownership monitoring and before/after integrity checks. This kernel-only sample weighting does not represent total response time.

The frozen table retains only four qualifying low-row cells: IQ2_XXS, IQ3_XXS and IQ3_S gate/up use mode 1; IQ4_NL down uses mode 2. Every other cell uses control. Gains occur in short final chunks; the predominant high-row class remains control. IQ2_XS/IQ2_S gate/up register demand rose to 160/158 per thread, preventing two-block residency even when three stages reduced shared memory. IQ4_NL down obtained two-block residency with three stages. Farther prefetch and a larger grid did not help combined microbenchmarks. No register caps, reduced precision, split-K, decoded model cache, expert-transfer changes, QSA work or upstream update was introduced.

## Disconnects and evidence exclusions

`disconnection-audit.json` retains all complete original samples, flags pair variation and lists excluded attempts. No fast/slow samples were removed to improve a result. Layout-preflight failure, empty routing-file benchmark attempts, the deliberately interrupted broad racecheck and foreign-GPU preflight rejection are preserved and excluded.

Final mode 5 parity, sanitizers, independent microbenchmarks and both new response profiles passed source/binary/fixture/model-file/configuration integrity checks on the same boot. UTC versus monotonic elapsed time showed no pause/discontinuity. Their binary SHA256 is `dbc526021a5c0103a8e3ff2f0aaf45bacfd19cbb6a1d2ea2343ba0656286ab04`. Full model/pack identity hashes and all 51 canonical fixture hashes are retained.

## Review, rollback and restoration

`campaign-only.patch` contains only this campaign's changes relative to the initial dirty working tree. `git apply --check -R` passed. Source snapshots, build/resource reports, frozen executables, library hashes, profiles, raw samples and final manifests are retained. The earlier full-tree patch also preserves existing work; use the isolated patch for review/rollback.

To remove the experiment while preserving prior changes:

```bash
cd /home/USER/opt/UnbiasedStrata
git apply -R local/benchmarks/expert-20261011T161207Z/campaign-only.patch
```

Optional workloads remain stopped. Restoration commands are in `restoration.sh`; choose `ornith`, `swift` or `none` to avoid restoring two GPU model services observed at different times. Production Strata is excluded. No rollout, wake scheduling, hibernation or further testing is authorized by this completed campaign.

Exact next action: review the retained patch/evidence if useful; keep mode 0 for production. This kernel campaign is closed at its profiling gate.
