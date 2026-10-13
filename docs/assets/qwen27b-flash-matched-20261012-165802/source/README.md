# bench — unattended multi-domain local-LLM benchmark suite

Ranks local models/configs on **executed** verdicts, across five domains, with
no agent and no LLM judge anywhere in the loop.

    packs/            one directory per domain (task data + builder + verifier)
    bench-run.py      the runner: lock -> launch target -> gate -> run -> grade -> teardown
    bench_lib.py      requests + timing harvest + the graders
    report.py         results/<tag>.json -> markdown scoreboard (+ Obsidian)
    campaign.sh       queue driver; this is what a timer/cron calls
    selftest.py       proves every grader accepts a known-good answer and rejects a bad one
    targets.json      every model+endpoint to rank (rig and Unraid side by side)
    results/          <tag>.json (per-task rows, crash-resumable) + <tag>.md

## Why it needs no babysitter

* **Execution is deterministic.** Tasks are graded by running code: hidden assert
  suites, end-state checks on a scratch directory, a behavioural verifier applied
  to a patched repo, real HTTP requests against the model's own server. No judge,
  so no agent has to read anything.
* **The runner is a plain process.** `campaign.sh` walks `queue.json`, runs each
  pending entry, writes the markdown, notifies, marks it done, exits. A systemd
  timer triggers it; an empty queue exits immediately.
* **Everything is crash-resumable.** Results are rewritten after EVERY task, so a
  kill, OOM or reboot costs one task. Re-running the same `--tag` (or `--retry`)
  keeps scored rows and only re-runs the rest — which is also why the unit can
  safely `Restart=on-failure`.
* **It cannot collide with your live server.** A single `flock` serialises
  campaigns, and a GPU target refuses to start while any foreign `llama-bench` /
  `llama-cli` process is alive. An endpoint that is **already serving is never
  torn down** — the runner only stops what it started.
* **It cannot measure a broken launch.** Before any task the runner fires one real
  completion and demands non-empty content; a target that fails the gate is
  skipped whole, so a 500-ing server can never poison a tag with fake zeros.

## Domains and how each is graded

| pack | shape | grading |
|---|---|---|
| `code` | 40 tiered tasks (bugfix/feature/algorithmic/hard) | model code exec'd against a hidden assert suite, per-assert partial credit |
| `research` | long-document QA over a generated 18K-token handbook | exact-value + section-citation marker match; arithmetic answers are provably absent from the document |
| `terminal` | multi-step shell/file work (log digests, broken harnesses, CSV repair, permission audit, manifest repair, lost git commit recovery) | run the model's script in a scratch dir, assert the END STATE (files, modes, contents, stdout); commands are never inspected |
| `backend` | implement-to-a-contract (token bucket, config layering, cursor pagination, idempotency store, migrations, a JSON HTTP service) | a hidden contract suite runs against the model's module, including real HTTP requests to the model's own server |
| `deepswe` | long-horizon multi-file repo changes (worker drain semantics, state-machine guards+history, layered CLI config) | the model returns a unified diff; it is applied to a fresh repo copy and the repo's own behavioural verifier decides. Any implementation satisfying the behaviour passes |
| `triage` | reference-only subset: hard tiers, one task per failure mode from all five domains | the ~20-task gate that decides whether a config deserves a full run |

`python3 selftest.py` runs every grader against a known-good reference solution
and a deliberately wrong one. Run it after ANY pack change: a broken grader
silently scores everything zero.

## Running it

    # one-off: everything, both endpoints, full packs
    ./bench-run.py --targets all --packs all --tag 2026-09-22-full

    # fast gate: hard subset only
    ./bench-run.py --targets rig-qwen38-27b-q5-mtp --packs triage --tag qwen-triage

    # resume a crashed run (keeps the rows already scored)
    ./bench-run.py --targets all --packs all --tag 2026-09-22-full --retry

    # markdown scoreboard (+ copy into the Obsidian vault)
    python3 report.py --tag 2026-09-22-full --vault

## Unattended operation

    # queue work (any number of entries; runs oldest-first on the next tick)
    ./campaign.sh --enqueue tag=nightly-qwen targets=rig-qwen38-27b-q5-mtp packs=all
    ./campaign.sh --enqueue tag=nightly-flash targets=rig-flashnext-ad384 packs=triage

    # run the queue now, or install the timer
    ./campaign.sh
    mkdir -p ~/.config/systemd/user
    cp systemd/bench-campaign.{service,timer} ~/.config/systemd/user/
    systemctl --user daemon-reload && systemctl --user enable --now bench-campaign.timer

`campaign.sh` notifies with `notify-send` when a run finishes or fails. On a
headless box replace that with whatever you actually read (ntfy, a Telegram
gateway delivery, a log line) — it is a two-line function at the top of the file.

## Two machines

`targets.json` treats every endpoint identically: `base_url` is all that matters,
`host` is documentation. So the rig can drive the Unraid endpoint over the LAN —
but only **one campaign may touch a machine's GPU at a time**, so the efficient
layout is one suite copy + one queue per machine:

    rsync -av ~/bench/ unraid:/mnt/user/bench/     # needs python3 on the target
    ssh unraid 'cd /mnt/user/bench && ./campaign.sh --enqueue tag=unraid-nightly targets=unraid-flashnext-iq3xxs-262k packs=all'

Both machines then bench in parallel on their own GPUs, and only the results
travel back (the JSON is self-contained; copy it into `results/` and
`report.py --tag ...` renders it locally).

## Targeting a config

A target entry says how the endpoint comes up:

    {"type": "none"}                          # already running (your live server, Unraid container)
    {"type": "systemd", "unit": "..."}        # systemctl --user start/stop
    {"type": "llama-switch", "arg": "mtp"}    # switch regimes via ~/.local/bin/llama-switch

`thinking` is part of the target, not the task, because thinking policy changes
results as much as the quant does: run the same model as separate targets
(`off` / `low` / `null`) instead of guessing one policy. `max_tokens` is the
per-target default; a task may set its own, plus `escalate: [16384, 32768]` —
escalation is attempted ONLY for the `finish_reason == "length"` failure mode,
so a model that is merely wrong never gets extra budget for free.

## Per-task row

`results/<tag>.json` keeps, per task: `ok/total` checks, `status`, the grader's
`detail`, the answer prefix, `wall_s`, `gen_n`, `decode_ts`, `prefill_ts`,
`ttft_s`, `prompt_n`, `finish_reason`, the token cap used and `attempts`. Quality
and speed therefore land in one artifact — no separate throughput run needed.

## Versioned contracts and Strata reasoning

The runner now defaults to `--suite-version contract-v2 --include-fixtures`. Repository source is included in prompts; hidden checks remain excluded. Historical contracts are available through `legacy` or frozen `contract-v1`. Always use a fresh tag when changing contracts, fixture inclusion or reasoning. `--resume` only runs unrecorded tasks and preserves recorded failures; it rejects incompatible settings.

Strata benchmark targets explicitly pin medium or low. Other clients that omit `reasoning_effort` still inherit the loaded model template's xhigh default. Set the API field to `"medium"` or `"low"`, or override a benchmark target with `--thinking medium|low|xhigh`. Launch configuration remains unchanged.

```bash
python3 selftest.py
python3 tools/selftest_contract_v2.py
python3 bench-run.py --targets strata-iq3-medium --packs deepswe2 --tag YOUR-FRESH-TAG --thinking medium --suite-version contract-v2 --include-fixtures
# Continue an interrupted campaign using exactly the same settings plus --resume.
```

See `results/strata-20261012-thinking-grader-investigation.md` for the reasoning pilot, grader audit and independently verified fresh campaign.
