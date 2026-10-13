#!/usr/bin/env python3
"""Unattended benchmark runner. No LLM in the loop, crash-resumable.

  ./bench-run.py --targets all --packs code,research --tag 2026-09-22-full
  ./bench-run.py --targets rig-flashnext-ad384 --packs triage --tag smoke --retry

Only ONE campaign may touch a machine at a time (flock). GPU targets additionally
refuse to start while a foreign llama-server/llama-bench process is alive, so a
campaign can never race a live inference server or a second bench.

Results land in results/<tag>.json after EVERY task, so a kill -9, OOM or reboot
costs at most the in-flight task. Re-running with --retry (or plain re-run: same
tag) keeps scored rows and re-runs only the unscored ones.
"""
import argparse
import hashlib
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench_lib import (RESULTS, ROOT, block, grade_assert, grade_cmd, grade_diff,
                       grade_files,
                       grade_markers, health_ok, load_pack, load_targets, mark,
                       request, strip_think, wait_health)

LOCK = os.path.join(ROOT, ".campaign.lock")
FOREIGN = ("llama-bench", "llama-cli", "llama-perplexity")


def acquire_lock():
    f = open(LOCK, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another campaign holds the lock — exiting")
        sys.exit(3)
    f.write(str(os.getpid()))
    f.flush()
    return f


def gpu_busy():
    """Return a description of any non-service llama process that would collide."""
    bad = []
    for b in FOREIGN:
        r = subprocess.run(["pgrep", "-x", b], capture_output=True, text=True)
        if r.stdout.strip():
            bad.append(b)
    return bad


def start_target(t):
    st = t.get("start", {"type": "none"})
    if st["type"] == "none":
        return False
    if st["type"] == "systemd":
        subprocess.run(["systemctl", "--user", "start", st["unit"]], check=True)
    elif st["type"] == "llama-switch":
        subprocess.run([os.path.expanduser("~/.local/bin/llama-switch"), st["arg"]], check=True)
    return True


def stop_target(t):
    st = t.get("start", {"type": "none"})
    if st["type"] == "systemd":
        subprocess.run(["systemctl", "--user", "stop", st["unit"]])
    elif st["type"] == "llama-switch":
        pass  # llama-switch stops the other regime itself; leave the new one serving
    return


def served_model(base_url, timeout=5):
    """First model id the endpoint reports, or None if it is not answering."""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=timeout) as r:
            d = json.loads(r.read())
        d = d.get("data") or d.get("models") or []
        if d:
            return d[0].get("id") or d[0].get("name")
    except Exception:
        return None
    return None


def is_right_server(t):
    """A live endpoint is only usable if it is serving the model this target
    claims. Otherwise it is the stale-server trap: the previous regime keeps
    answering and the whole tag gets attributed to the wrong config."""
    got = served_model(t["base_url"])
    if not got:
        return False
    want = t.get("expect_model")
    if not want:
        print(f"  endpoint serving {got!r} (no expect_model set — trusting it)")
        return True
    ok = want.lower() in got.lower()
    if not ok:
        print(f"  endpoint serves {got!r}, target wants {want!r} — switching")
    return ok


def gate(t, readiness_tokens=2048):
    """A real completion, because /health ok does not mean requests work."""
    try:
        # 256 tokens, not 16/64: a reasoning model can burn a small cap entirely
        # inside the thought phase and return empty content, which would look
        # like a broken server. (Measured: Ornith MTPv2 answers at ~34 tokens
        # total, so any cap below that reads as a dead endpoint.)
        r = request([{"role": "user", "content": "Reply with the single word: ready"}],
                    t.get("model"), t["base_url"], max_tokens=readiness_tokens,
                    thinking=t.get("thinking"), timeout=300)
    except Exception as e:
        print(f"  GATE FAILED: {type(e).__name__}: {e}")
        return False
    if not (r.get("final_text", r["text"]) or "").strip() or not (r.get("gen_n") or 0):
        print(f"  GATE FAILED: no generated text (finish={r['finish_reason']}, "
              f"gen_n={r.get('gen_n')})")
        return False
    shown = strip_think(r.get("final_text", r["text"])).strip()
    print(f"  gate ok: {shown[:40]!r}  {r['wall_s']}s")
    return True


def build_messages(task, include_fixtures=False):
    msgs = []
    if task.get("system"):
        msgs.append({"role": "system", "content": task["system"]})
    user = task["prompt"]
    if include_fixtures and task.get("kit") and "__tree__" not in task["kit"]:
        sources = []
        for path, content in sorted(task["kit"].items()):
            sources.append("=== " + path + " ===\n" + content)
        user = "Repository/working-directory files (existing contents):\n" + "\n\n".join(sources) + "\n\nTask:\n" + user
    if include_fixtures and task.get("kind") == "shell":
        user += "\nReturn one complete ```bash block that performs the task. You may invoke Python inside the Bash script."
    if task.get("corpus_text"):
        user = ("Document:\n<<<DOC\n" + task["corpus_text"] + "\nDOC>>>\n\n" + user)
    msgs.append({"role": "user", "content": user})
    return msgs


def grade(task, r):
    kind = task.get("kind", "assert")
    txt = r.get("final_text", r["text"])
    if kind == "assert":
        code = block(txt, "python") or block(txt)
        return grade_assert(code, task["tests"])
    if kind == "qa" and task.get("grading_contract") == "contract-v2":
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from bench_contract_v2 import grade_research_contract_v2
        return grade_research_contract_v2(strip_think(txt), task["required"], task.get("banned", ()))
    if kind == "qa":
        return grade_markers(strip_think(txt), task["required"], task.get("banned", ()))
    if kind in ("shell", "pyfile", "repo"):
        return grade_cmd(txt, task.get("lang", "bash"), task.get("kit"),
                         task["check"], timeout=task.get("timeout", 180),
                         save_as=task.get("save_as"))
    if kind == "diff":
        return grade_diff(txt, task.get("kit"), task["check"],
                          timeout=task.get("timeout", 180))
    if kind == "files":
        return grade_files(txt, task.get("kit"), task["check"],
                           timeout=task.get("timeout", 180))
    return 0, 1, f"unknown-kind:{kind}"


def run_task(t, task, default_maxtok, include_fixtures=False, seed=40):
    caps = [task.get("max_tokens") or default_maxtok] + list(task.get("escalate", []))
    best = None
    history = []
    for i, cap in enumerate(caps):
        attempt_started = time.perf_counter()
        try:
            r = request(build_messages(task, include_fixtures), t.get("model"), t["base_url"],
                        max_tokens=cap, seed=task.get("seed", seed),
                        thinking=t.get("thinking"))
        except Exception as e:
            best = {"ok": 0, "total": 1, "detail": f"req-error:{type(e).__name__}",
                    "wall_s": round(time.perf_counter() - attempt_started, 1), "gen_n": None, "decode_ts": None, "prefill_ts": None,
                    "ttft_s": None, "finish_reason": None, "maxtok": cap, "attempts": i + 1}
            history.append(dict(best, error=str(e), effective_seed=task.get("seed", seed)))
            break
        ok, total, detail = grade(task, r)
        r["_answer"] = r.get("final_text", strip_think(r["text"]))
        best = {"ok": ok, "total": total, "detail": detail, "wall_s": r["wall_s"],
                "gen_n": r["gen_n"], "decode_ts": r["decode_ts"],
                "prefill_ts": r["prefill_ts"], "ttft_s": r["ttft_s"],
                "finish_reason": r["finish_reason"], "maxtok": cap, "attempts": i + 1,
                "prompt_n": r["prompt_n"],
                "_answer": r["_answer"]}
        history.append(dict(best, effective_seed=task.get("seed", seed), raw_answer=r["text"], response_message=r.get("response_message")))
        if ok == total:
            break
        # only the truncated-output failure mode is worth more budget
        if r["finish_reason"] != "length":
            break
    best["effective_seed"] = task.get("seed", seed)
    best["attempt_history"] = history
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default="all")
    ap.add_argument("--packs", default="all")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--seed", type=int, default=40)
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--thinking", choices=["low", "medium", "xhigh"], help="explicit request reasoning effort")
    ap.add_argument("--include-fixtures", action=argparse.BooleanOptionalAction, default=True, help="provide existing kit files and declare shell output format")
    ap.add_argument("--suite-version", choices=["legacy", "contract-v1", "contract-v2"], default="contract-v2", help="versioned benchmark contract corrections")
    ap.add_argument("--resume", action="store_true", help="skip all recorded rows, including failures")
    ap.add_argument("--readiness-tokens", type=int, default=2048)
    ap.add_argument("--limit", type=int, default=0, help="max tasks per pack (smoke runs)")
    ap.add_argument("--roles", default="", help="comma list of task roles to keep "
                    "(batch-research,obscure-research,agentic,deepswe); empty = all")
    a = ap.parse_args()

    lock = acquire_lock()
    all_t = load_targets()
    tids = list(all_t) if a.targets == "all" else a.targets.split(",")
    packdir = os.path.join(ROOT, "packs")
    pnames = sorted(d for d in os.listdir(packdir)
                    if os.path.exists(os.path.join(packdir, d, "pack.json"))
                    or os.path.exists(os.path.join(packdir, d, "tasks.json")))
    if a.packs != "all":
        pnames = [p for p in a.packs.split(",")]
    if a.suite_version == "contract-v2":
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from bench_contract_v2 import load_contract_v2_pack
        packs = [load_contract_v2_pack(p) for p in pnames]
    elif a.suite_version == "contract-v1":
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from bench_corrected_suite import load_corrected_pack
        packs = [load_corrected_pack(p) for p in pnames]
    else:
        packs = [load_pack(p) for p in pnames]

    fingerprints = {t["id"]: {"task": hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest(), "message": hashlib.sha256(json.dumps(build_messages(t, a.include_fixtures), sort_keys=True).encode()).hexdigest(), "check": hashlib.sha256(t.get("check", "").encode()).hexdigest()} for p in packs for t in p["tasks"]}
    out_path = os.path.join(RESULTS, f"{a.tag}.json")
    doc = json.load(open(out_path)) if os.path.exists(out_path) else \
        {"tag": a.tag, "created": time.time(), "targets": {}}
    if doc.get("suite_version") and doc["suite_version"] != a.suite_version:
        raise ValueError("Use a fresh tag when changing the suite version")
    if "include_fixtures" in doc and doc["include_fixtures"] != a.include_fixtures:
        raise ValueError("Use a fresh tag when changing fixture inputs")
    if doc.get("fingerprints", fingerprints) != fingerprints or doc.get("seed", a.seed) != a.seed:
        raise ValueError("Resume fingerprint or seed mismatch")
    doc.update(fingerprints=fingerprints, seed=a.seed)
    print(f"campaign {a.tag}: targets={tids} packs={[p['name'] for p in packs]}")
    print(f"tasks: {sum(len(p['tasks']) for p in packs)}  out={out_path}")

    for tid in tids:
        t = dict(all_t[tid])
        if a.thinking:
            t["thinking"] = a.thinking
        previous = doc["targets"].get(tid, {}).get("configuration")
        if previous and previous != t:
            raise ValueError("Use a fresh tag when changing thinking policy")
        doc["targets"].setdefault(tid, {"rows": [], "notes": t.get("notes")})
        rows = doc["targets"][tid]["rows"]
        done = {r["id"] for r in rows if a.resume or (a.retry and r.get("status") == "pass")}
        print(f"\n=== {tid}  ({t['base_url']})  {len(rows)} rows so far")

        busy = gpu_busy()
        if t.get("gpu") and busy:
            print(f"  REFUSING: foreign GPU processes alive: {busy} — fix, then rerun")
            continue
        already = health_ok(t["base_url"]) and is_right_server(t)
        if already:
            print("  right server already up — will not tear it down")
        started = False
        if not already and (t.get("gpu") or t["start"]["type"] != "none"):
            started = start_target(t)
        if not wait_health(t["base_url"], timeout_s=900):
            print("  endpoint never became healthy — skipping target")
            if started:
                stop_target(t)
            continue
        if not already and t.get("start", {}).get("type") == "none":
            raise RuntimeError("endpoint-only target identity/health mismatch")
        if not gate(t, a.readiness_tokens):
            print("  gate failed — skipping target (a bad launch must not poison the tag)")
            if started:
                stop_target(t)
            continue

        doc["targets"][tid]["configuration"] = t
        doc["include_fixtures"] = a.include_fixtures
        doc["suite_version"] = a.suite_version
        doc["targets"][tid]["served_model"] = served_model(t["base_url"])
        t0 = time.time()
        roles = set(x for x in a.roles.split(",") if x)
        for p in packs:
            tasks = p["tasks"][:a.limit] if a.limit else p["tasks"]
            if roles:
                tasks = [t for t in tasks if t.get("role") in roles]
            for task in tasks:
                rid = f"{p['name']}/{task['id']}"
                if rid in done:
                    continue
                res = run_task(t, task, t.get("max_tokens", 8192), a.include_fixtures, a.seed)
                full_answer = res.pop("_answer", "") or ""
                row = {"id": rid, "pack": p["name"], "task": task["id"],
                       "answer": full_answer[:400],
                       "domain": task.get("domain", p["name"]), "tier": task.get("tier"),
                       "role": task.get("role", "-"),
                       "status": "pass" if res["ok"] == res["total"] else
                                 ("part" if res["ok"] else "fail"),
                       **res}
                # full untruncated answers enable offline re-grading when the
                # grader contract changes (2026-09-23 lesson: the [:400] cap
                # made the flash conformance-tax un-auditable post-hoc)
                with open(os.path.join(RESULTS, f"{a.tag}.answers.jsonl"), "a") as af:
                    af.write(json.dumps({"id": rid, "answer": full_answer}) + "\n")
                rows[:] = [r for r in rows if r["id"] != rid] + [row]
                doc["targets"][tid]["wall_s"] = round(time.time() - t0, 1)
                with open(out_path, "w") as f:
                    json.dump(doc, f, indent=1)
                print(f"  {mark(res['ok'], res['total']):4s} {rid:34s} "
                      f"{res['ok']}/{res['total']}  {res.get('decode_ts') or 0} t/s  "
                      f"{res['wall_s']}s" + (f"  [{res['detail'][:48]}]"
                                             if res["ok"] != res["total"] else ""),
                      flush=True)
        if started:
            stop_target(t)
        print(f"  target wall: {round(time.time()-t0,1)}s")

    # summary
    print("\n================ SUMMARY ================")
    for tid, d in doc["targets"].items():
        rows = d["rows"]
        if not rows:
            continue
        ok = sum(r["ok"] for r in rows)
        tot = sum(r["total"] for r in rows)
        full = sum(1 for r in rows if r["status"] == "pass")
        dts = [r["decode_ts"] for r in rows if r.get("decode_ts")]
        print(f"{tid}: {ok}/{tot} checks | {full}/{len(rows)} full | "
              f"median decode {sorted(dts)[len(dts)//2] if dts else '-'} t/s | "
              f"wall {d.get('wall_s')}s")
        for tier in sorted({r.get("tier") or "-" for r in rows}):
            tr = [r for r in rows if (r.get("tier") or "-") == tier]
            print(f"    {tier:5s} {sum(r['ok'] for r in tr)}/{sum(r['total'] for r in tr)} "
                  f"checks, {sum(1 for r in tr if r['status']=='pass')}/{len(tr)} full")
    print(f"results: {out_path}")
    lock.close()


if __name__ == "__main__":
    main()