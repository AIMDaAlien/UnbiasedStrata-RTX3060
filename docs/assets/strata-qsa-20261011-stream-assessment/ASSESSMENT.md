# QSA streaming top-k assessment — follow-up, 2026-10-11

The targeted PR743 branch is complete without a new port. Its intended improvement—coalesced score reads on each radix pass—is already present in the current wide kernel and already selected by the frozen RTX 3060 control at 128K and 180K. No source edits, build, GPU parity test or performance run were performed. Production remains unchanged and stopped.

## Immutable evidence

[PR743](https://github.com/Niko1221/Strata/pull/743) is closed and unmerged. Inspected commit [83cf4dd1a4dc97852b22970cf379ee689be89a93](https://github.com/Niko1221/Strata/commit/83cf4dd1a4dc97852b22970cf379ee689be89a93), archived its patch, commit metadata, original source and discussion. Later maintainer discussion identifies duplicate streaming capability and a narrow Turing dispatch adjustment; the author's remeasurement describes end-to-end differences within noise and the original long-context improvement as already covered by the wide kernel. Those are upstream observations, not measurements on this machine.

## Selection contract and comparison

Both kernels use one 1024-thread CTA per query, capacity-based score-row stride, live NKv/NBid/selection width from steps, four descending 8-bit weighted radix passes and the same ordered float key transform. Full blocks contribute four cells, the partial block contributes its remaining cells, and zero-weight entries are ignored. The threshold includes higher-score blocks first; equal-score cells consume the residual budget in increasing block/cell order. Output contains ascending selected cell IDs; unused padding is outside the contract.

The radix-loop bodies are identical after removing comments/whitespace and renaming the local histogram-fold accumulator. `normalized-radix.txt` records the comparison. **The full kernels are different:** current wide performs emission with warp-owned ascending contiguous regions and warp scans; the PR kernel performs ascending CTA-wide chunks and block scans. This assessment does not assert new runtime parity or compare their performance. An emission rewrite would need exact selected-ID tests, especially tied cutoffs, partial blocks and scan synchronization, before any timing.

On CUDA, the current register limit is 33792 blocks. With ACTIVE_ANY=0 and context capacity 196608, reach follows score stride 49154, so the frozen control already selects wide at 128K/180K. Early prompt batches below 4608 live blocks retain the existing reference fallback. The proposed original PR dispatch additionally requires a counted active bound; that condition is false for the frozen RTX 3060 control. Enabling it unchanged would therefore add no dispatched treatment. Changing dispatch or duplicating emission would be a different experiment with no established incremental gain.

Prior `parity.json` documents exact IDs across both capacities and ACTIVE_ANY modes for the existing code; it is copied as historical evidence only. Prior raw profiling logs establish actual wide dispatch. No fresh parity or speed claim is made.

## Next measured bottleneck

| Frozen control request | Fused expert gate/up + down | Profiled prefill | Share |
|---|---:|---:|---:|
|128K|35.364s|150.2058s|23.5437%|
|180K|49.838s|217.5899s|22.9046%|

This is the largest individually reported phase. Fused down compute is charged to gate/up. The residual QSA-selection phase contains scoring plus top-k; its 7.498%/10.267% shares cannot be attributed entirely to top-k. Expert development, GDN and KV changes remain outside this follow-up.

An unrelated `/usr/bin/llama-server` process (PID 12096, 9314 MiB) currently uses the GPU. It was recorded and left running; it is not the reason for the technical stop decision. No hibernation or other power action was requested or performed this morning.
