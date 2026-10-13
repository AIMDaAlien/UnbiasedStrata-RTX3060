# Expert campaign handoff

Completed all four implementation families and independently checked the frozen mode 5 table. Exact parity and required sanitizers passed. Fresh final 128K/180K quality passed, but candidate/control total-response ratios were 1.001219 and 1.001797, failing the <=0.95 profiling gate. Screening and acceptance were not warranted and were not run.

Disconnection-era measurements are selection evidence only. Final checks used the same frozen binary, timestamps/boot IDs, exclusive GPU ownership at 100 W and clean integrity/clock-continuity checks. Failed/incomplete/empty/foreign-GPU attempts remain excluded.

Production source selection defaults to 0. Production configuration, binary and launcher are unchanged, and production is stopped. Optional workloads remain stopped; `restoration.sh` contains manual commands. No experiment or helper process remains running.

Next action: review `REPORT.md` and `campaign-only.patch`; this campaign is closed. Rollback with the isolated reverse patch preserves initial dirty changes. No rollout or further testing is scheduled.
