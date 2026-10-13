# RX 9060 XT investigation

The installed Radeon is gfx1200, confirmed by `amdgpu-arch`. This fork's
`cmake/hip_backend.cmake` explicitly lists gfx1200 as a community-validated
architecture for its retained HIP engine. An AMD-only build is therefore a
reasonable first experiment using this fork's existing source.

The C++ app target was gated on `STRATA_ENABLE_CUDA`. The local change also
creates it for `STRATA_ENABLE_HIP`, using the existing HIP runtime target and
compatibility include paths. Build and artifact handling still use the pinned
submodule and local files. The original Python server is not launched.

This change does NOT implement mixed AMD/NVIDIA inference. CUDA and HIP remain
separate builds. In particular, `RemoteExperts::preflight` enumerates devices
through `cudaGetDeviceCount` (mapped to HIP in a HIP build), and its expert
cache uses allocations and streams from that same runtime. A CUDA build cannot
enumerate the Radeon; a HIP build cannot enumerate the NVIDIA card. Removing
the front end's single-GPU argument checks does not change this.

A plausible mixed-vendor implementation would keep the NVIDIA main engine
and run a separate HIP expert worker on the Radeon. It would need a local IPC
protocol for expert ownership, batched activations/routing and results, shared
host buffers with correct synchronization, HIP-side quantized expert kernels,
bounded memory allocation, failure handling and integration with both the decode
and speculative verification paths. The local boundary should have no network
client or external endpoint. CPU expert fallback and a feature flag would let
the bridge be compared with the current single-GPU path. Performance must be
measured: extra copies and per-layer synchronization can consume the benefit.

Before building that bridge, validate the AMD-only engine on the actual RX 9060:

1. Provide an environment with GPU devices visible (`/dev/dri` and `/dev/kfd`)
   and the ROCm HIP development toolkit and hipBLAS available.
2. Run `~/opt/UnbiasedStrata/local/build-amd.sh`.
3. Discover the Radeon device's HIP/ROCr identity with `rocminfo`; select the
   discrete gfx1200 GPU explicitly so the gfx1036 integrated GPU is not chosen.
4. Run the launcher with the prepared AMD config and the appropriate
   `ROCR_VISIBLE_DEVICES` setting. This is an AMD-only test on port 18082:

   ```sh
   ROCR_VISIBLE_DEVICES=<discrete-GPU-UUID-or-index> \
     strata --config ~/opt/UnbiasedStrata/local/config-amd.json
   ```

5. Verify `/health`, real completions, tool calls and streaming; compare greedy
   responses with the CUDA path and measure prompt/decode time, GPU activity,
   CPU activity and expert-cache behavior before designing the mixed path.

Do not run both full model servers simultaneously on this 64 GB machine. The
test launcher does not itself apply the installed user service's memory cap;
use a temporary user service with `MemoryMax=56G` and `MemorySwapMax=0` for
the AMD loading experiment, as the existing benchmark runner does.

Current verification: CUDA rebuild and local launcher validation only. The
current sandbox has no `/dev/dri` or `/dev/kfd`, `vulkaninfo` cannot enumerate
a GPU, NVIDIA driver access fails, and the ROCm HIP toolkit/hipBLAS are absent.
The AMD build has NOT compiled or run, and no mixed-GPU performance gain is
claimed. The existing CUDA profile remains selected.

## Decode-only assistance with NVIDIA prefill

The experimental `amd_decode_only: true` profile field adds
`--amd-decode-only` to the C++ engine command. AMD retains disjoint expert
ownership for decode, but the pinned CPU complement also retains these expert
blobs so NVIDIA prefill can stream the entire model. The prefill object is not
given the AMD helper, keeping its streaming tables and fused path consistent.
GPU-cache adaptation continues to exclude the AMD-owned pairs.

Full AMD prefill with explicitly requested fused kernels is rejected. Removing
that restriction would require coherent buffer sizing, streaming ownership and
prefill kernels, rather than changing the fused conditional. AMD remains off in
production pending the existing six-bucket/five-pair performance and quality gate.

### Tuned NVIDIA comparison — 2026-10-11

Decode-only AMD was screened against the five-pair-validated fused NVIDIA profile (auto ceiling 16384, ring512). All quality checks passed with zero helper fallback, but the six-bucket geometric-mean ratio was 1.00986 and every bucket was slower. The screen missed the 10% improvement gate, so AMD stays disabled; no five-pair AMD acceptance was warranted. See [prefill results](PREFILL_RESULTS.md) and [AMD decision](benchmarks/prefill-20261010/amd-decision.json).
