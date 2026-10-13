# Local long-context and AMD expert experiment

Production remains on the existing single-3060 profile until the automated quality,
memory and timing gates pass. The 3060 stays at 100 W. No model, RoPE setting,
original Python server or system power setting is changed.

## Run and resume

Stop production inference before testing. The runner starts one temporary user
service at a time with `MemoryMax=56G`, `MemorySwapMax=0` and bounded shutdown.

```sh
cd /home/USER/opt/UnbiasedStrata
local/build-amd.sh
build/strata-amd-helper-check local/amd-worker.sh GPU-8140af32fe338274 \
  /home/USER/opt/Strata-data/models/IQ3_XXS/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf \
  local/pack-iq3_xxs
python local/long_experiment.py --output local/benchmarks/long-20261010-v3 --apply
```

The same output directory resumes completed measurements; interrupted runs are
rerun. `local/experiment.log` contains progress for the current invocation.
`--apply` writes production settings only after a complete passing baseline;
AMD additionally needs the five paired acceptance repetitions. Omit it for a
read-only experiment. The production service is not enabled or started by the
runner. Config and OpenCode context changes receive timestamped backups.

## Worker boundary

`strata-amd-worker` is a separate HIP executable for gfx1200. The CUDA engine
keeps attention, routing, KV, sampling, MTP and combination. An inherited Unix
`SOCK_SEQPACKET` socket carries versioned commands. A sealed-size `memfd` carries
at most 256 activation rows, 2,560 result rows and one 4 MiB weight staging buffer.
There is no network listener, network client or telemetry in the worker.

The worker uses one quantized expert arena, at most 12 GiB and no more than free
VRAM minus 2 GiB after its scratch allocations. NVIDIA and AMD assignments are
disjoint; static AMD assignments are excluded from NVIDIA adaptive admission and
CPU residency. NVIDIA's borrowed prefill slots retain their existing RAM backing.
Prefill launches AMD batches alongside NVIDIA work and waits before combination.
Decode and verification use the same helper boundary alongside the CPU pool.

Commands and responses carry monotonically increasing sequence and generation
numbers. Failure terminates and reaps the worker before reading shared buffers,
then recomputes all affected rows on CPU. Cancellation invalidates the generation.
The diagnostic executable checks real expert weights, batch widths 1/4/256,
interleaved routing, worker death, stale responses, cancellation and shutdown.

Opt in explicitly through launcher config keys `amd_helper`, `amd_device` and
`amd_vram_mib`, or the matching executable flags `--amd-helper PATH`,
`--amd-device ROCr-UUID`, `--amd-vram-mib N`. `local/config-amd-helper.json` is an
experimental profile; it is not the production config.

## Measurement and acceptance

The capacity is 196,608 tokens. `/tokenize` uses the inference chat template and
tokenizer to construct exact inputs at 80,000, 128,000 and 180,000 tokens. Growing
fixtures add roughly 8K tokens and include generated assistant and tool-call
turns. Tool definitions remain stable to preserve normal prefix reuse.
Canonical saved requests are replayed for paired runs, so prior response text
differences cannot change the task or context payload. Token counts are checked
against actual completion usage. Retrieval selects first, middle and last
records across the full conversation. Code checks cover merging intervals,
ordering completed results and bounded batching; model code is checked in a
separate process with restricted syntax/builtins, CPU/memory limits and timeout.

Both modes screen 8/12/15/16 workers, MTP drafts 2/4 and five KV configurations:
INT8, k8v4, q4_0, INT8 with a 32K resident window, and INT8 with a 64K window.
The two fastest passing candidates per KV precision receive 180K verification.
Complete fresh/growing verification then covers all six workload buckets.

Results include client wall time, TTFT, cumulative conversation wall time, cached
prompt tokens, engine prefill/decode time, draft acceptance, CPU activity, cgroup
memory peak/swap, disk reads and both GPUs' memory/activity. Helper logs separate
host staging, HIP transfers, kernel time and host waiting. Startup is separate.
Failed, truncated, incomplete, swapped or lost-state runs are excluded. Helper
fallback is tested for correctness but excludes a performance candidate.

Five paired repetitions alternate mode order. `paired_report.py` uses each
repetition's log geometric mean across the six buckets and a paired t interval
(five repetitions, four degrees of freedom). Enablement requires a geometric
mean ratio <= 0.90, upper paired 95% interval < 1 and every bucket ratio <= 1.05.
Growing buckets use cumulative conversation time; fresh buckets use request time.
Paired KV precision, fixtures, output budgets and reasoning settings must match.

`decision.json` records the evidence and rollout decision. Restoration uses the
timestamped `config.json.before-long-context-*` and corresponding OpenCode backup.
The original UnbiasedStrata and Strata rollback paths remain available.

## 2026-10-10 result

The production profile is now IQ3_XXS, 196,608 context, 12 workers, four MTP
drafts, INT8 KV with a 32K resident window. It passed fresh and growing quality
checks at 80K, 128K and 180K with no swap. The fixture explicitly asks the
model not to call tools for the self-contained retrieval/code task; growing
tool-call turns remain independently checked.

AMD passed quality, but its one paired feasibility run was slower in all six
buckets (geometric mean time ratio 1.432; individual ratios 1.38–1.57). The
plan's early-stop rule was met, so five repetitions were not run and AMD stays
disabled. At 80K, it changed peak RTX 3060 VRAM by only 22 MiB while using about
12.3 GiB on the RX 9060 XT; host memory peaked at the 56 GiB cap in both modes.
See `benchmarks/long-20261010-v4/decision.json` and the paired run records for
the complete measurements.
