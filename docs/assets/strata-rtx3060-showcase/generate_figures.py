#!/usr/bin/env python3
"""Regenerate the Strata RTX 3060 showcase figures from retained reports."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator


VAULT = Path(__file__).resolve().parents[2]
ASSET_DIR = Path(__file__).resolve().parent
EVIDENCE = Path("/home/USER/opt/UnbiasedStrata/local")
PREFILL_CSV = VAULT / "assets/strata-prefill-20261010/response-times.csv"
ACCEPTANCE_JSON = EVIDENCE / "benchmarks/prefill-20261010/decision.json"
EXPERT_DIR = EVIDENCE / "benchmarks/expert-20261011T161207Z"

BG = "#101820"
PANEL = "#172630"
GRID = "#354650"
TEXT = "#edf3f4"
MUTED = "#a9bbc2"
BLUE = "#58a6ff"
GREEN = "#4bd3a4"
AMBER = "#ffbd5c"
RED = "#ff6b6b"
PURPLE = "#bb9af7"


def theme() -> None:
    plt.rcParams.update({
        "figure.facecolor": BG,
        "axes.facecolor": PANEL,
        "axes.edgecolor": GRID,
        "axes.labelcolor": TEXT,
        "text.color": TEXT,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.titleweight": "bold",
        "savefig.facecolor": BG,
        "svg.fonttype": "none",
    })


def read_acceptance():
    with PREFILL_CSV.open(newline="") as f:
        rows = list(csv.DictReader(f))
    decision = json.loads(ACCEPTANCE_JSON.read_text())
    return rows, decision


def accepted_chart() -> None:
    rows, decision = read_acceptance()
    labels = [f"{r['workload'].title()} · {int(r['context_tokens']) // 1000}K" for r in rows]
    baseline = np.array([float(r["baseline_seconds"]) for r in rows])
    tuned = np.array([float(r["tuned_seconds"]) for r in rows])
    savings = np.array([float(r["paired_time_saved_percent"]) for r in rows])
    ci_low, ci_high = decision["paired_95_ci_ratio"]
    overall = decision["wall_time_improvement_percent"]

    fig = plt.figure(figsize=(15.4, 8.6), layout="constrained")
    gs = fig.add_gridspec(3, 2, height_ratios=[0.6, 3.4, .24], width_ratios=[3.2, 1.15])
    head = fig.add_subplot(gs[0, :]); head.set_axis_off()
    head.text(0.01, 0.78, "STRATA · RTX 3060 · ACCEPTED NVIDIA PREFILL TUNING", color=GREEN,
              fontsize=11, weight="bold", transform=head.transAxes)
    head.text(0.01, 0.18, f"{overall:.2f}% less total response time",
              fontsize=27, weight="bold", transform=head.transAxes)
    head.text(0.99, 0.26, f"Paired 95% CI · candidate / original\n{ci_low:.5f}–{ci_high:.5f}  (n = {decision['paired_repetitions']} pairs)",
              fontsize=11, color=MUTED, ha="right", va="bottom", transform=head.transAxes)

    ax = fig.add_subplot(gs[1, 0])
    y = np.arange(len(rows)); h = .34
    ax.barh(y + h/2, baseline, h, color=BLUE, label="Original", zorder=3)
    ax.barh(y - h/2, tuned, h, color=GREEN, label="Tuned", zorder=3)
    for yi, b, t in zip(y, baseline, tuned):
        ax.text(b + 3, yi + h/2, f"{b:.1f} s", va="center", color=TEXT, fontsize=9)
        ax.text(t + 3, yi - h/2, f"{t:.1f} s", va="center", color=TEXT, fontsize=9)
    ax.set_yticks(y, labels); ax.invert_yaxis()
    ax.set_xlim(0, max(baseline) * 1.2)
    ax.set_xlabel("Completed response time (seconds)")
    ax.set_title("All six measured workload buckets", loc="left", pad=12)
    ax.grid(axis="x", color=GRID, alpha=.7, zorder=0)
    ax.legend(frameon=False, ncols=2, loc="upper right")

    ax2 = fig.add_subplot(gs[1, 1])
    colors = [BLUE if r["workload"] == "fresh" else PURPLE for r in rows]
    ax2.barh(y, savings, color=colors, height=.56, zorder=3)
    for yi, val in zip(y, savings):
        ax2.text(val + .55, yi, f"{val:.2f}%", va="center", weight="bold", fontsize=10)
    ax2.set_yticks(y, ["" for _ in y]); ax2.invert_yaxis()
    ax2.set_xlim(0, max(savings) * 1.3)
    ax2.set_xlabel("Less time · paired (%)")
    ax2.set_title("Paired savings", loc="left", pad=12)
    ax2.grid(axis="x", color=GRID, alpha=.7, zorder=0)
    foot = fig.add_subplot(gs[2, :]); foot.set_axis_off()
    foot.text(.01, .5, "Fresh = new request. Growing = cumulative conversation through each checkpoint, including tool turns. Five alternating pairs; quality and workload checks passed.", color=MUTED, fontsize=9, va="center")
    for ext in ("png", "svg"):
        fig.savefig(ASSET_DIR / f"accepted-response-times.{ext}", dpi=190, bbox_inches="tight")
    with (ASSET_DIR / "accepted-response-times.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["workload", "context_tokens", "original_seconds", "tuned_seconds", "paired_time_saved_percent"])
        for r in rows:
            w.writerow([r["workload"], r["context_tokens"], r["baseline_seconds"], r["tuned_seconds"], r["paired_time_saved_percent"]])
    plt.close(fig)


def expert_chart() -> None:
    summary = json.loads((EXPERT_DIR / "final-profile-summary.json").read_text())
    gate = json.loads((EXPERT_DIR / "profile-gate.json").read_text())
    micro = json.loads((EXPERT_DIR / "mode5-independent-report.json").read_text())
    kernel_ratio = micro["combined_ratio_by_mode"]["5"]
    kernel_gain = (1 - kernel_ratio) * 100

    records = []
    for length in (128000, 180000):
        control = next(x for x in summary["control"] if x["target_tokens"] == length)
        candidate = next(x for x in summary["candidate"] if x["target_tokens"] == length)
        ratio = gate["profiled_total_response_ratios"][str(length)]
        records.append((length, control["total_response_seconds"], candidate["total_response_seconds"], (ratio - 1) * 100))

    fig = plt.figure(figsize=(14.6, 7.0), layout="constrained")
    gs = fig.add_gridspec(2, 2, height_ratios=[1, .18], width_ratios=[.9, 2.0])
    head = fig.add_subplot(gs[0, 0]); head.set_axis_off()
    right = fig.add_subplot(gs[0, 1])
    fig.suptitle("NATIVE FUSED EXPERT CAMPAIGN · PROFILING GATE REJECTED", x=.03, ha="left", fontsize=17, weight="bold", color=RED)
    head.text(.06, .80, f"−{kernel_gain:.2f}%", transform=head.transAxes, fontsize=34, weight="bold", color=GREEN)
    head.text(.06, .65, "sampled combined kernel time", transform=head.transAxes, fontsize=12, color=TEXT)
    head.text(.06, .47, "Mode 5 independent microbenchmark", transform=head.transAxes, fontsize=10, color=MUTED)
    head.text(.06, .14, "Microbenchmark only.\nNot an end-to-end speed result.", transform=head.transAxes, color=AMBER, fontsize=11, weight="bold")
    head.set_title("Kernel samples", loc="left", pad=12)

    y = np.arange(2); h = .34
    ctr = [r[1] for r in records]; cand = [r[2] for r in records]
    right.barh(y + h/2, ctr, h, color=BLUE, label="Control", zorder=3)
    right.barh(y - h/2, cand, h, color=RED, label="Mode 5 candidate", zorder=3)
    for yi, row, c, t in zip(y, records, ctr, cand):
        right.text(c + 1.2, yi + h/2, f"{c:.3f} s", va="center", fontsize=10)
        right.text(t + 1.2, yi - h/2, f"{t:.3f} s", va="center", fontsize=10)
        right.text(256, yi, f"+{row[3]:.3f}% slower", va="center", color=AMBER, fontsize=10, weight="bold", ha="left")
    right.set_yticks(y, ["Fresh · 128K", "Fresh · 180K"]); right.invert_yaxis()
    right.set_xlim(0, 290); right.set_xlabel("Profiled completed response time (seconds)")
    right.set_title("Instrumented final profiles · excluded from acceptance statistics", loc="left", pad=12)
    right.grid(axis="x", color=GRID, alpha=.7, zorder=0); right.legend(frameon=False, loc="lower right")
    foot = fig.add_subplot(gs[1, :]); foot.set_axis_off()
    foot.text(.01, .5, "Required gate: at least 5% total response-time reduction at both lengths. Observed ratios: 1.001219 (128K), 1.001797 (180K). No screening or acceptance run followed.", color=MUTED, fontsize=9, va="center")
    for ext in ("png", "svg"):
        fig.savefig(ASSET_DIR / f"expert-campaign-gate.{ext}", dpi=190, bbox_inches="tight")
    with (ASSET_DIR / "expert-campaign-gate.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["evidence_type", "workload", "control_seconds", "candidate_seconds", "candidate_control_ratio", "change_percent", "interpretation"])
        w.writerow(["independent microbenchmark", "sampled combined expert kernels", "", "", kernel_ratio, -kernel_gain, "kernel-only reduction; not response time"])
        for row in records:
            length, c, t, slower = row
            w.writerow(["instrumented final profile", f"fresh-{length//1000}K", c, t, 1 + slower/100, slower, "slower; profiling gate failed; excluded from acceptance statistics"])
    plt.close(fig)


COMPONENT_RE = re.compile(r"([a-zA-Z+ /-]+?)\s+(\d+)\s+\(([\d.]+)%\)")


def parse_components(text: str) -> dict[str, tuple[float, float]]:
    prefix = text.split(" ms:", 1)[1]
    result = {}
    for name, ms, pct in COMPONENT_RE.findall(prefix):
        result[name.strip()] = (float(ms), float(pct))
    return result


def bottleneck_chart() -> None:
    summary = json.loads((EXPERT_DIR / "final-profile-summary.json").read_text())
    profiles = {}
    for length in (128000, 180000):
        row = next(x for x in summary["control"] if x["target_tokens"] == length)
        profiles[length] = parse_components(row["existing_prefill_timing"])

    # The top-level `gdn` timer overlaps its detailed measurements. Exclude it;
    # combine the three disjoint reported GDN subcomponents as one visual group.
    gdn_children = ("gdn conv+gates", "gdn recurrence", "gdn out proj")
    common = [k for k in profiles[128000] if k not in ("gdn", *gdn_children)]
    names = []
    for k in common:
        if k == "gemm gate/up":
            names.append("Expert GEMM · gate/up")
        elif k == "qsa select":
            names.append("QSA selection")
        elif k == "qsa proj":
            names.append("QSA projection")
        elif k == "qsa indexer":
            names.append("QSA indexer")
        elif k == "qsa attn":
            names.append("QSA attention")
        elif k == "hc read":
            names.append("Host-cache read")
        elif k == "kv stage":
            names.append("KV staging")
        elif k == "router+shared":
            names.append("Router + shared")
        elif k == "embed+steps":
            names.append("Embedding + steps")
        elif k == "wait copy":
            names.append("Copy wait")
        else:
            names.append(k.title())
    names.append("GDN component group")
    values = {length: [] for length in profiles}
    seconds = {length: [] for length in profiles}
    for length, data in profiles.items():
        for k in common:
            ms, pct = data[k]; values[length].append(pct); seconds[length].append(ms / 1000)
        gdn_ms = sum(data[k][0] for k in gdn_children)
        gdn_pct = sum(data[k][1] for k in gdn_children)
        seconds[length].append(gdn_ms / 1000); values[length].append(gdn_pct)

    order = np.argsort(np.array(values[180000]))
    names = [names[i] for i in order]
    fig = plt.figure(figsize=(13.8, 9.4), layout="constrained")
    gs = fig.add_gridspec(2, 1, height_ratios=[1, .10])
    ax = fig.add_subplot(gs[0])
    y = np.arange(len(names)); h = .34
    c128 = [values[128000][i] for i in order]; c180 = [values[180000][i] for i in order]
    gdn_idx = names.index("GDN component group")
    colors = [PURPLE if i == gdn_idx else (AMBER if "Expert GEMM" in name else BLUE) for i, name in enumerate(names)]
    for i, (a, b, col) in enumerate(zip(c128, c180, colors)):
        ax.barh(i + h/2, a, h, color=col, alpha=.68, zorder=3)
        ax.barh(i - h/2, b, h, color=col, zorder=3)
        ax.text(a + .18, i + h/2, f"{a:.1f}%", va="center", fontsize=9, color=MUTED)
        ax.text(b + .18, i - h/2, f"{b:.1f}%", va="center", fontsize=9)
    ax.set_yticks(y, names); ax.invert_yaxis(); ax.set_xlim(0, max(c180) * 1.25)
    ax.set_xlabel("Share of prefill GPU timeline (%)")
    ax.set_title("Fresh-request prefill profile · frozen control", loc="left", fontsize=17, pad=14)
    ax.grid(axis="x", color=GRID, alpha=.7, zorder=0)
    ax.legend(handles=[plt.Rectangle((0,0),1,1,color=BLUE,alpha=.68,label="128K"), plt.Rectangle((0,0),1,1,color=BLUE,label="180K")], frameon=False, ncols=2, loc="lower right")
    foot = fig.add_subplot(gs[1]); foot.set_axis_off()
    foot.text(.01, .68, "GDN combines conv+gates, recurrence and output projection; the overlapping aggregate ‘gdn’ timer is omitted.", color=MUTED, fontsize=9, va="center")
    foot.text(.01, .18, "Largest measured phase: expert GEMM gate/up. Untested opportunities: GDN kernels, QSA/attention and KV overlap.", color=MUTED, fontsize=9, va="center")
    for ext in ("png", "svg"):
        fig.savefig(ASSET_DIR / f"prefill-bottleneck.{ext}", dpi=190, bbox_inches="tight")
    with (ASSET_DIR / "prefill-bottleneck.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["component", "context_tokens", "seconds", "prefill_gpu_timeline_percent", "aggregation_note"])
        for length in profiles:
            for i, name in enumerate(names):
                note = "sum of conv+gates, recurrence, output projection; overlapping aggregate gdn timer excluded" if i == gdn_idx else "reported component"
                w.writerow([name, length, seconds[length][order[i]], values[length][order[i]], note])
    plt.close(fig)


if __name__ == "__main__":
    theme()
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    accepted_chart()
    expert_chart()
    bottleneck_chart()
