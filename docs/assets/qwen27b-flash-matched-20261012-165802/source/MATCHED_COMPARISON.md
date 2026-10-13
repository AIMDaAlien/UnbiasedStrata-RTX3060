# Matched Qwen 27B versus Flash comparison

Approved scope: six local contract-v2 DeepSWE2 campaigns, in order Qwen-40, Flash-40, Flash-41, Qwen-41, Qwen-42, Flash-42. Use medium reasoning, temperature zero, frozen task budgets, full repository fixtures, and task-specific seeds when present. Keep Ornith inactive throughout and afterward.

Completed execution prefix: `qwen27b-flash-matched-20261012-165802`.
Inactive controller unit: `bench-matched-controller-v2.service`.
Completed read-only provenance monitor: `bench-matched-monitor.service`.
Artifacts: `/home/USER/bench/results/<prefix>*`.

The earlier prefix ending `165741` failed before any scoring because an empty Vulkan visibility variable hid devices. The corrected launch unsets that variable, with Vulkan1 = RX 9060 XT and Vulkan2 = RTX 3060. No benchmark configuration was tuned during scoring.

`tools/run_matched_qwen_flash.py` launches a fresh process for every campaign, records identity/arguments/executable hashes, preserves campaign rows, rejects incompatible resumption, and cleans up transient units without restarting Ornith. To resume an interrupted controller, first verify no benchmark process remains, then run:

```bash
python3 tools/run_matched_qwen_flash.py qwen27b-flash-matched-20261012-165802
```

Do not restart a live controller or change the suite/configuration. Completed campaigns are skipped; all recorded task failures are preserved. A campaign's `bench-run.py --resume` skips every recorded row.

`tools/matched_analysis.py <manifest>` independently materializes and regrades every final answer, verifies all 144 rows and equal task/message/check fingerprints, runs separate public behavioral probes, and writes a paired task-ID bootstrap report. `tools/matched_probes.py` with no arguments validates probes on corrected references. Its initial early e1/e8 probe assumptions were too strict and were corrected in the explicitly superseding `early-probes.v2.json`; raw campaign grading was unchanged.

Completion requires six 24-row campaigns, independent audit, focused review of disagreements and hard passes, final report, stopped benchmark servers, and inactive Ornith. Background launch alone is not completion.

Completed: Qwen 21/24 in all three repeats; Flash 23/24, 22/24, 23/24. Mean Flash advantage +1.67 tasks, task-bootstrap 95% interval [-2.33, +5.67]. All 144 frozen-score regrades agree. Report and PNG/SVG delta/trade-off charts are in `results/qwen27b-flash-matched-20261012-165802.*`. Benchmark servers and Ornith are inactive.
