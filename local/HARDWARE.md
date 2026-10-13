# Local installation and hardware findings

Installed 2026-10-10. UnbiasedStrata commit `d0a44ea7e757c59fa35a78b4b98d0c4bb44ce2cf`;
llama.cpp submodule `3cf03257f219afbe7334045ff7c6a06ac68c627d`.

## Actual hardware

- Ryzen 9 7950X: 16 physical cores, 32 logical CPUs, AVX-512 available.
- RAM: 64 GB installed, approximately 62 GiB visible to Linux.
- NVIDIA RTX 3060: 12 GiB VRAM, 100 W cap. Keep this cap per the user's measurements.
- AMD RX 9060 XT: approximately 16 GiB VRAM.
- AMD integrated Raphael graphics also detected.
- Only one RTX 3060 is currently installed. Old configs and benchmark notes refer to two.

## What changed

`~/opt/UnbiasedStrata/build/unbiased-strata` is built in Release mode with CUDA `sm_86`,
`STRATA_PORTABLE=OFF` and `GGML_NATIVE=ON`. CPU compilation uses `-march=native`.
Strata's AVX-512 expert kernels retain their runtime CPU checks.

Existing IQ3_XXS model shards and MTP files are reused. The prepared local pack links to
the existing dense/native-expert metadata and contains a copy of the old expert profile.
No model download is necessary. The source tree's generated `local/` directory is untracked.

`~/.local/bin/strata` and the old `~/opt/Strata/run-iq3_xxs.sh` launch the new engine.
The original launcher remains in `run-iq3_xxs.sh.before-unbiasedstrata`.
The old Strata source, binary, server and model files remain available for rollback.
OpenCode's `local-strata/strata` provider keeps `http://127.0.0.1:8081/v1` and now
advertises a 32768-token context instead of the old dual-GPU 114688-token setting.
Its backup is `~/.config/opencode/opencode.json.before-unbiasedstrata`.
Other OpenCode providers and the selected default model are preserved.

The fork provides an OpenAI-compatible API, not the original Python Strata browser UI.
Use OpenCode or another OpenAI-compatible client with the endpoint above.

## Initial hardware profile (not yet benchmarked)

Settings are in `~/.config/unbiasedstrata/config.json`:

- 15 expert worker threads, plus the engine's participating host thread, use the 16
  physical cores without initially adding a seventeenth CPU expert worker.
- 32K context and INT8 KV storage leave more VRAM for experts than the old 128K setup.
- GPU expert cache and prefill chunk sizing remain automatic.
- MTP speculative decoding remains enabled with a four-token draft.
- GPU/CPU shared-expert overlap, graph capture, adaptive expert caching and the host
  thread's participation remain enabled; serial A/B debug modes are not selected.
- `--resident-experts` keeps the GPU cache's CPU complement in RAM when possible,
  with an 8 GiB headroom setting. The engine can fall back to partial residency/mmap.
- `--ple-io direct` avoids touching/loading the approximately 27 GB n-gram table in
  full, preserving RAM for the much hotter expert weights; uses the existing SSD.
- The user service caps its own RAM at 56 GiB and disables swap for that workload.
  It is not enabled at login, and was not started in this session.
- Existing system memory-lock limits and GPU power settings are unchanged.

These choices are plausible starting points, not evidence of maximum throughput.
Direct PLE I/O, available RAM, PCIe transfers, expert-cache hit rates and the number
of CPU workers can all affect idle gaps. Validate with representative prompts.

## Start and measure (run from your normal desktop terminal)

```sh
systemctl --user daemon-reload
systemctl --user start unbiasedstrata.service
journalctl --user -u unbiasedstrata.service -f
```

Loading can take several minutes. The health endpoint appears only after loading:

```sh
curl http://127.0.0.1:8081/health
curl http://127.0.0.1:8081/v1/models
```

For measurement, stop the inference service first:

```sh
systemctl --user stop unbiasedstrata.service
strata-benchmark --full --apply
systemctl --user start unbiasedstrata.service
```

The sweep tests 8, 12, 15 and 16 CPU workers with four- and two-token MTP drafts.
Each profile gets a warm-up and two repeats of short and longer prompts. Each
request has distinct text near the start to prevent full prompt-cache reuse.
It records end-to-end throughput, engine prompt/decode timing, draft acceptance,
CPU core-equivalents busy and GPU utilization, memory-controller activity,
VRAM and power samples. Profiles run serially in temporary user services with
memory caps. It refuses to run while the installed service is active or if less
than 10000 MiB of NVIDIA VRAM is free. Stop any other model server first.

Results and logs go into `local/benchmarks/<timestamp>/`. `--apply` saves the fastest
complete profile on this particular workload after backing up the config. It does
not alter power limits, context length or the selected OpenCode default model.
This sweep is not an exhaustive workload study: its fixed run order can favor later
profiles through disk-cache warming; compare close results on your own agent tasks.
Average utilization over a whole request also mixes prompt and decode phases.
More CPU threads can lose to memory bandwidth or contention; a busy GPU is not by
itself proof of faster useful output. There is one conversation/request at a time
in this fork, so it also cannot fill idle time with parallel client decoding.

## One versus two RTX 3060s, and mixed AMD/NVIDIA

Upstream documentation: https://github.com/robertkarl/UnbiasedStrata

The fork documents one NVIDIA GPU with at least 24 GB VRAM and 128 GB RAM. This
12 GB/64 GB machine is below that documented configuration. The engine contains
small-card/low-RAM paths, which the launcher selects, but successful GPU execution
and throughput on this machine remain unverified.

The fork explicitly rejects `--gpus`, `--layer-split`, `--split-device`,
`--peer-device`, `--peer-slots`, `--remote-expert` and `--batch`. A second 3060
therefore adds no supported acceleration to this installed front end. Two 12 GB
cards also do not meet its requirement for one 24 GB card.

Original Strata supported multiple NVIDIA GPUs. The saved `Documents/Obsidian/Strata
Bench.md` reports approximately 48 tokens/s and 732.2 seconds for a 40-task suite
on this rig's prior dual-3060 configuration. That is historical evidence, not a
controlled comparison against today's single-card fork. Only one 3060 is available
now, so a live one-versus-two comparison cannot be performed.

This CUDA build cannot compute on the RX 9060 XT. The source's CUDA and HIP builds
are mutually exclusive; its remote-expert tier addresses another device through
the same CUDA/HIP runtime, rather than bridging vendors. Using the AMD card to
accelerate this same model would require a different runtime with compatible
mixed-vendor support or substantial engine changes. In this installation the AMD
card can serve the desktop or a separate AMD-compatible workload, but its VRAM
cannot be pooled with the 3060's for this fork.

For the requested fork, keep the single 3060 at 100 W and measure the CPU/cache
profile. If accelerating one model across two 3060s is the priority, the original
multi-GPU Strata engine is the relevant path. If using both current vendors for
the same model is the priority, this fork does not provide that capability.

## Verification and current limitation

### IQ3_S fit evidence

The existing IQ3_S files total 83.618 GB (77.875 GiB), versus 75.840 GB
(70.632 GiB) for IQ3_XXS. Both contain the same 28.800 GB second shard.
The IQ3_S native expert pack contains 50.292 GB (46.84 GiB) of experts,
versus 42.913 GB (39.97 GiB) for IQ3_XXS: about 6.87 GiB more expert RAM.
GGUF file size is not the required resident RAM: PLE can be read from disk,
and GPU-resident experts need not all be duplicated in the resident CPU copy.

The old `~/opt/Strata/strata-iq3_s.log` records successful loading of 46.84 GiB
of experts and actual generation around 39.5–40.3 tokens/s with two RTX 3060s.
Thus IQ3_S previously ran on this rig's original Strata installation. This is
historical evidence for the prior dual-GPU configuration, not a current test
of the single 3060 or of UnbiasedStrata, whose documented model is IQ3_XXS.
64 GB RAM can run IQ3_S with selective residency/SSD reads, but is tight for
the full expert set plus desktop/engine buffers; loading the whole PLE table
into RAM would make the fit substantially worse. 128 GB gives more headroom
and can reduce file-cache eviction, but does not guarantee a throughput gain
if the run is already limited by compute or transfers rather than disk waits.

Release build, native CPU compiler flags, binary help, Python syntax, prepared
artifact paths, launcher command generation and systemd unit verification passed.
Systemd verification emitted sandbox socket warnings but no invalid-unit errors.

The session permissions changed to a managed sandbox after hardware detection.
NVIDIA driver access and the user D-Bus/service manager became unavailable.
`nvidia-smi` then failed to communicate with the driver. A startup attempt failed
before readiness at native embedding allocation/pinning; see `startup-check.log`.
This is not a valid test of the physical machine's GPU memory capacity. No live
API response, GPU performance result, full utilization result or optimum is claimed.

## Rollback

Stop the new service, then restore the saved launcher and OpenCode config:

```sh
systemctl --user stop unbiasedstrata.service
cp ~/opt/Strata/run-iq3_xxs.sh.before-unbiasedstrata ~/opt/Strata/run-iq3_xxs.sh
cp ~/.config/opencode/opencode.json.before-unbiasedstrata ~/.config/opencode/opencode.json
```

The old dual-GPU config still needs to be changed for the currently installed
single NVIDIA card before it can run successfully. Rebuild the new binary, if
needed, with `~/opt/UnbiasedStrata/local/build.sh`.
