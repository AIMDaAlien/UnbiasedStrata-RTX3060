# RTX 3060 optimization research — 2026-10-10

Scope: existing IQ3_XXS, 196608 context, 100 W RTX 3060, 56 GiB cgroup,
no swap, original quality fixtures. Original Python server is excluded.

## Sources and applicability

- [Upstream details](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md):
  native IQ fused prefill is opt-in; published measurements are mostly on a
  5070, not this Ampere card. Tensor-core support starts at SM80, and local
  source accepts this SM86 card. Tile heuristics were measured on a 5070.
  Explicit execution-log confirmation and local measurements are necessary.
- [Issue 954](https://github.com/Niko1221/Strata/issues/954) and
  [PR 958](https://github.com/Niko1221/Strata/pull/958): version 0.1.39 can
  shrink fused buffers even when a layer requires the full FP16 fallback.
  Guard the local pinned source before exploring larger chunks; do not assume
  disabling the byte-budget ring fixes the underlying allocation defect.
- [KV prefetch](https://github.com/Niko1221/Strata/blob/main/docs/KV_PREFETCH.md):
  overlapping streamed KV copies helped a historical SM86 two-card setup,
  but the upstream port has incomplete runtime validation. This pinned engine
  lacks the feature. Porting requires staging-buffer release/ready events,
  error-path draining, relayout handling and cancellation tests. Only pursue
  if local KV-stage timing warrants the complexity.
- [Stager spin issue 1056](https://github.com/Niko1221/Strata/issues/1056) and
  [transient-source issue 1353](https://github.com/Niko1221/Strata/issues/1353):
  source classification can select many copy workers even for cached data;
  yield loops and inherited CPU affinity can then starve the launch thread.
  Inspect actual residency and host-staging time before tuning workers or
  introducing blocking waits. Local full pinned residency avoids most copies.
- [NVIDIA CUDA best practices](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html):
  batching and pinned-memory asynchronous copies can reduce transfer costs;
  overlap needs separate streams and explicit ordering. The local NVIDIA
  expert source already uses pinned residency and a streaming ring. Merely
  adding pinned buffers cannot remove its measured expert-transfer volume.

## Initial local profile

The new profiled baseline passed the unchanged 80K fresh quality fixture:
122.39 s completed-response time. GPU prefill timeline was 115.96 s.
Copy waits accounted for 26.2%; expert dequantization 4.3%, gate/up GEMM 10.7%,
down GEMM 6.2%. Hyper-connection read was 7.4%. KV stage was 0.6% and PLE
0.3%. Events attribute waits to the phase on the compute stream; these are
critical-path diagnostics, not independent device copy-engine utilization.

## Ranked candidates

1. Fused native IQ3 kernels, automatic then forced 64/128 tiles. Smaller MoE
   scratch and fused expert work may reduce memory traffic and cache borrowing.
2. Raise automatic chunk ceiling to 16384 (then 32768 only if measured useful).
   Fewer chunks stream each layer fewer times, but attention scratch and cache
   loans can offset the gain. Record resolved size, ring and cache slots.
3. One ring override at a time after chunk selection: compare 128/256/512 as
   supported. A smaller ring saves cache slots but can increase transfer waits.
4. Host staging workers/ring only if host time or residency shows actual copies.
5. CPU cache/profile/MTP only after profiling completed growing conversations.
   Fresh 80K decode was about 5 s, leaving little room for a total-time win.
6. AMD decode-only with the best NVIDIA prefill. Keep AMD pairs in the pinned
   CPU expert complement and omit AMD from prefill ownership/routing tables.
   Preserve disjoint decode ownership and existing fallback. Full AMD prefill
   remains excluded from fused mode, rather than removing the exclusion.

Existing AMD full-prefill feasibility was 1.432 times baseline wall time and
slower in all six buckets. At 80K helper device compute was 42.63 s, transfer
5.54 s, and host wait 57.89 s (overlapping quantities; do not add them).
A larger bounded HIP prefill kernel is a separate project only if decode-only
results and a compute/communication profile support it. Transfer-only work
cannot plausibly recover this gap on the present scalar-row helper.

## Experimental integrity

The old systemd benchmark forwarded only three variables. The launchers now
forward allowed optimization controls, record them and the binary SHA-256,
and verify them in the live process. Profile overrides work in production too.
No arbitrary shell secrets are copied. Profiling runs screen candidates;
acceptance runs omit instrumentation, alternate order for five paired repeats,
and preserve canonical request hashes. Failures and incomplete outputs are
excluded. Single-GPU acceptance requires a paired 95% upper time ratio below 1
and no bucket over 1.05. AMD additionally requires overall ratio at most 0.90.

Original binary rollback: build/unbiased-strata.before-prefill-tuning.
The passing NVIDIA candidate is applied at ~/.config/unbiasedstrata/config.json.
[Application record](benchmarks/prefill-20261010/application.json) contains rollback paths;
[results](PREFILL_RESULTS.md) distinguish final acceptance from screens.

## Ring and PCIe follow-up

The source scans pinned share before allocating the resident cache complement.
The initial mmap source therefore can select the 96-slot unpinned heuristic,
even though later the fully pinned complement exceeds 90% of expert bytes.
Changing that classification after allocating RAM would invalidate the already
planned cache loan/backing. Environment ring overrides are safer for this
experiment because planning and residency see the same setting throughout.
The link is healthy at PCIe Gen4 x4 under load (7.88 GB/s theoretical per direction);
6.4 GB/s measured H2D is plausible for that link. No hardware change is proposed.

Automatic fused tile and forced 64 screened at 119.25 and 119.22 seconds respectively.
That difference does not justify a forced tile. The first fusion screen is only
2.6% faster and needs paired validation; screen numbers are not production claims.

## Completed 80K screening sweep

These are one-request screens with profiling, not the five-pair acceptance result.

| Setting | Completed seconds | Resolved chunk | Ring | Borrowed slots |
|---|---:|---:|---:|---:|
| current | 119.26 | 8192 | 96 | 1754 |
| chunk16384 | 100.79 | 13568 | 96 | 2668 |
| chunk32768 | 100.70 | 13568 | 96 | 2668 |
| ring128 | 101.35 | 13312 | 128 | 2666 |
| ring256 | 96.63 | 12288 | 256 | 2662 |
| ring512 | 94.37 | 10496 | 512 | 2694 |

The selected screen candidate is native fusion with automatic tile sizing,
`STRATA_PREFILL_AUTO_MAX=16384`, `STRATA_PREFILL_RING=512`. It resolves to
10496 tokens on this machine. The original profiled baseline was 122.39 s;
the candidate was 94.37 s. Every screen passed the unchanged 80K quality checks.
Five alternating paired repetitions across all six buckets passed. The aggregate
completed-response improvement was 16.58%, with paired 95% time-ratio CI
[0.83366, 0.83473]. See [results](PREFILL_RESULTS.md).

The fused diagnostic called “host staging” includes waits around asynchronous
copy issue; its 107 s value is not a host memcpy measurement. GPU event phases
and completed-response time are the useful comparisons here.

