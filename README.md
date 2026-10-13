# UnbiasedStrata RTX 3060 snapshot — 2026-10-12

A personal hardware-constrained experiment on one RTX 3060 (12 GiB, 100 W), Ryzen 9 7950X and 64 GB RAM. This is a full-source patch snapshot of existing runtimes, not a new engine or a claim of general model superiority. No ongoing upstream tracking, new-model support or maintenance commitment is offered.

Ancestry: [Strata](https://github.com/Niko1221/Strata) → [UnbiasedStrata](https://github.com/robertkarl/UnbiasedStrata) → this snapshot. Niko1221 and the Strata contributors authored the engine; robertkarl authored the UnbiasedStrata frontend and packaging. AIMDaAlien's local work adds hardware profiles, frontend reasoning/token-count handling, prefill tuning and instrumentation, safety guards, opt-in AMD/kernel experiments, and evidence/documentation packaging. AI agents assisted implementation and packaging. MIT licenses and attribution are retained; model licenses are separate.

Pinned base: `d0a44ea7e757c59fa35a78b4b98d0c4bb44ce2cf`; llama.cpp: `3cf03257f219afbe7334045ff7c6a06ac68c627d`. The default branch is `rtx3060-snapshot`, release `rtx3060-2026-10-12`. Parent branch history is preserved. No newer upstream source is merged.

## What was measured

- The combined fused-prefill/chunk/ring profile reduced response time by **16.58%** across six saved long-context buckets, after five alternating pairs. Candidate/control paired 95% interval: **0.83366–0.83473**. This describes repeatability on these fixtures and this machine.
- AMD assistance, native expert-kernel candidates and the QSA active-bound candidate failed their rollout gates. They remain opt-in; no accepted end-to-end improvement is attributed to them.
- The corrected matched comparison averaged **22.67/24 Flash versus 21/24 Qwen**, with paired task-bootstrap difference interval **[-2.33, +5.67]**. Quantization, runtime, context, KV, speculation and device allocation differ; these tasks do not resolve general model superiority.

[Quick start](docs/QUICKSTART.md) · [Models and preparation](docs/MODELS.md) · [Experiments and rollback](docs/EXPERIMENTS.md) · [Verification](snapshot/verification.json) · [Export provenance](docs/export-manifest.json) · [Upstream ancestry](UPSTREAM.md)

## Evidence and notes

The five selected Obsidian notes and relevant small evidence archives are exported under [docs/notes](docs/notes). Their original measurements and executable identities remain authoritative; rebuilding this snapshot does not repeat a benchmark. The scored campaigns are not rerun for packaging.

An on-demand, one-way export is available:

```sh
python3 scripts/export-notes.py --vault "$OBSIDIAN_VAULT"
python3 scripts/check-docs.py
```

This reads the five selected notes, converts wiki links/embeds, copies relevant assets and records original/exported checksums. It normalizes personal home paths and omits the unrelated desktop handoff. References outside the export become plain text. No background synchronization, automatic publishing or edits to vault originals occur. Evidence scripts under `docs/assets` are historical snapshots, not relocated runnable benchmarks.

Weights, prepared packs, executables, caches and bulk experiment output are excluded. Download the patch against the pinned base from the [release](https://github.com/AIMDaAlien/UnbiasedStrata-RTX3060/releases/tag/rtx3060-2026-10-12). Future work, if any, receives a separate dated snapshot.
