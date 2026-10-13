#!/usr/bin/env python3
"""Render readable benchmark charts from the accepted paired measurements."""
import argparse
import csv
import json
import statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--results', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
decision = json.loads((args.results / 'decision.json').read_text())
pairs = [[json.loads((args.results / f'paired/{i}/{name}/results.json').read_text())
          for name in ('baseline', 'candidate')] for i in range(5)]
rows = []
for workload in ('fresh', 'growing'):
    metric = 'wall_seconds' if workload == 'fresh' else 'conversation_wall_seconds'
    for context in (80000, 128000, 180000):
        times = [statistics.mean(next(r[metric] for r in pair[k]['runs']
                 if r['workload'] == workload and r['target_tokens'] == context)
                 for pair in pairs) for k in (0, 1)]
        ratio = decision['bucket_ratios'][f'{workload}-{context}']
        rows.append(dict(workload=workload, context_tokens=context,
                         baseline_seconds=times[0], tuned_seconds=times[1],
                         paired_time_saved_percent=100 * (1 - ratio)))
with (args.output / 'response-times.csv').open('w') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 19,
                     'svg.fonttype': 'none', 'axes.titleweight': 'bold'})
fig = plt.figure(figsize=(14, 12.8), facecolor='white')
ink, muted = '#172b3a', '#475569'
colors = ('#687c91', '#087f8c')
fig.text(.065, .961, 'Long-context responses finish sooner', fontsize=27,
         weight='bold', color=ink)
fig.text(.065, .922, 'RTX 3060 at 100 W  ·  IQ3_XXS  ·  five alternating pairs',
         fontsize=19, color=muted)
fig.text(.065, .877, f"{decision['wall_time_improvement_percent']:.2f}% less time overall", fontsize=24, weight='bold', color=colors[1])
fig.legend(handles=[Patch(color=colors[0], label='Original settings'),
                    Patch(color=colors[1], label='Tuned NVIDIA')],
           loc='upper right', bbox_to_anchor=(.97, .89), frameon=False, fontsize=18)

for index, workload in enumerate(('fresh', 'growing')):
    bottom = .55 if index == 0 else .18
    ax = fig.add_axes([.16, bottom, .65, .235])
    title = 'Fresh request' if workload == 'fresh' else 'Growing conversation'
    subtitle = 'One complete response, starting with an empty cache' if workload == 'fresh' else 'Cumulative elapsed time through each checkpoint, including tool turns'
    fig.text(.065, bottom + .292, title, fontsize=23, weight='bold', color=ink)
    fig.text(.065, bottom + .262, subtitle, fontsize=17, color=muted)
    group = [row for row in rows if row['workload'] == workload]
    for y, row in enumerate(group):
        for k, field in enumerate(('baseline_seconds', 'tuned_seconds')):
            pos = y + (-.19 if k == 0 else .19)
            value = row[field]
            ax.barh(pos, value, height=.30, color=colors[k], zorder=3)
            ax.text(value + 6, pos, f'{value:.1f} s', va='center', fontsize=19,
                    color=ink, weight='bold' if k else 'normal')
        ax.text(1.06, y, f"{row['paired_time_saved_percent']:.1f}%", fontsize=22,
                color=colors[1], weight='bold', va='center',
                transform=ax.get_yaxis_transform(), clip_on=False)
    ax.text(1.06, 1.04, 'Time saved', transform=ax.transAxes, color=muted, fontsize=17)
    ax.set_yticks(range(3), ['80K tokens', '128K tokens', '180K tokens'])
    ax.set_ylim(2.55, -.55)
    ax.set_xlim(0, 470)
    ax.set_xticks([0, 100, 200, 300, 400])
    ax.set_xlabel('Elapsed seconds  ·  lower is faster', fontsize=18, color=muted, labelpad=11)
    ax.tick_params(axis='both', length=0, pad=10, labelcolor=ink, labelsize=18)
    ax.grid(axis='x', color='#dce4e9', linewidth=1, zorder=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
fig.text(.065, .066, 'Bars show mean seconds; savings use paired geometric-mean ratios.',
         fontsize=17, color=muted)
fig.text(.065, .036, f"Overall 95% interval: {100*(1-decision['paired_95_ci_ratio'][1]):.2f}–{100*(1-decision['paired_95_ci_ratio'][0]):.2f}% less time. Same machine and fixtures.",
         fontsize=17, color=muted)
for ext in ('png', 'svg'):
    fig.savefig(args.output / f'response-times.{ext}', dpi=180, facecolor='white')
plt.close(fig)
print('Wrote chart PNG, scalable SVG and source CSV to', args.output)
