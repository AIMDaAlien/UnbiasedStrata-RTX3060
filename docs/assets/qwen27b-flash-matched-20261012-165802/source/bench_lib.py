#!/usr/bin/env python3
"""Core helpers for the bench suite. Stdlib only, no deps, no LLM in the loop.

Everything the runner needs: target discovery, OpenAI-compatible requests with
timing harvest, code extraction, and a scratch-dir grader.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
PACKS = os.path.join(ROOT, "packs")
RESULTS = os.path.join(ROOT, "results")


# ---------------------------------------------------------------- targets
def load_targets(path=None):
    path = path or os.path.join(ROOT, "targets.json")
    with open(path) as f:
        t = json.load(f)
    return {x["id"]: x for x in t["targets"]}


def health_ok(base_url, timeout=5):
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def wait_health(base_url, timeout_s=900):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if health_ok(base_url):
            return True
        time.sleep(3)
    return False


# ---------------------------------------------------------------- requests
def request(messages, model, base_url, max_tokens=4096, temperature=0.0,
            seed=40, thinking=None, timeout=5400):
    """One chat completion. thinking: None | 'off' | 'low' | 'medium' | 'high'."""
    body = {"messages": messages, "max_tokens": max_tokens,
            "temperature": temperature, "seed": seed}
    if model:
        body["model"] = model
    if thinking == "off":
        body["chat_template_kwargs"] = {"enable_thinking": False}
    elif thinking:
        body["chat_template_kwargs"] = {"reasoning_effort": thinking}
    data = json.dumps(body).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                 data=data,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    wall = time.perf_counter() - t0
    ch = d["choices"][0]
    msg = ch.get("message", {})
    txt = msg.get("content") or ""
    if not txt and msg.get("reasoning_content"):
        txt = msg["reasoning_content"]          # keep the trace when content is empty
    tm = d.get("timings", {}) or {}
    out = {
        "text": txt,
        "final_text": msg.get("content") or "",
        "reasoning_text": msg.get("reasoning_content") or "",
        "response_message": msg,
        "wall_s": round(wall, 1),
        "finish_reason": ch.get("finish_reason"),
        "gen_n": tm.get("predicted_n", (d.get("usage") or {}).get("completion_tokens")),
        "prefill_ts": round(tm["prompt_n"] / tm["prompt_ms"] * 1000, 1) if tm.get("prompt_ms") else None,
        "decode_ts": round(tm["predicted_n"] / tm["predicted_ms"] * 1000, 1) if tm.get("predicted_ms") else None,
        "ttft_s": round(tm["prompt_ms"] / 1000, 2) if tm.get("prompt_ms") else None,
        "cache_n": tm.get("cache_n"),
        "prompt_n": tm.get("prompt_n"),
    }
    return out


# ---------------------------------------------------------------- extraction
def block(text, lang=None):
    """Longest fenced block, optionally language-filtered."""
    pat = r"```([A-Za-z0-9_+-]*)\s*\n(.*?)```"
    best, best_l = "", None
    for m in re.finditer(pat, text or "", re.S):
        if lang and m.group(1).lower() not in (lang, "") and m.group(1).lower() != lang:
            continue
        if len(m.group(2)) > len(best):
            best, best_l = m.group(2), m.group(1)
    return best


def blocks(text, lang=None):
    pat = r"```([A-Za-z0-9_+-]*)\s*\n(.*?)```"
    out = []
    for m in re.finditer(pat, text or "", re.S):
        if lang and m.group(1).lower() not in (lang, ""):
            continue
        out.append(m.group(2))
    return out


def agent_code(text):
    """Tool-call dialect fallback: pull runnable shell out of agent-style
    tool-call answers. Tool-call-emitting models (flash-next) answer terminal
    tasks with `<tool_call><function=Bash><parameter=command>...`, JSON tool_use
    blobs, or ```json {"name":"bash","arguments":{"command":...}}``` instead
    of a raw fenced shell block. End-state grading only cares whether the
    commands run, so we extract the command payloads. Returns '' when no
    dialect is present (never fires for normal fenced answers)."""
    text = text or ""
    cmds = []
    # antml-style: <tool_call> ... <function=X> ... <parameter=command|cmd|script> BODY </parameter> ... </function> ... /antml
    for m in re.finditer(
            r"<parameter=(?:command|cmd|script)>\s*\n?(.*?)</parameter>",
            text, re.S):
        body = m.group(1).strip()
        if body:
            cmds.append(body)
    # JSON tool_use: {"name": "...", "arguments": {"command": "..."}}
    for m in re.finditer(r'\{\s*"name"\s*:[^{}]*?"arguments"\s*:\s*\{[^{}]*?"command"\s*:\s*("(?:[^"\\]|\\.)*")', text, re.S):
        try:
            cmds.append(json.loads(m.group(1)))
        except Exception:
            pass
    return "\\n".join(cmds)


def strip_think(text):
    return re.sub(r"<(think|thinking|reasoning)>.*?</\1>", "", text or "", flags=re.S).strip()


# ---------------------------------------------------------------- grading
def _run_grader(args, capture_output=False, text=False, timeout=None, **kwargs):
    """Timeout the complete scratch process group, including spawned children."""
    if capture_output:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    proc = subprocess.Popen(args, text=text, start_new_session=True, **kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        raise
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)


def count_asserts(tests):
    return len(re.findall(r"^\s*assert\b", tests, re.M)) or 1


def grade_assert(code, tests, timeout=30):
    """Exec the model's code together with a hidden assert suite. Returns
    (checks_passed, checks_total, detail)."""
    total = count_asserts(tests)
    if not code.strip():
        return 0, total, "no-code"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.py")
        with open(p, "w") as f:
            wrapped = re.search(r"^def run\(ns\):", tests, re.M)
            invoked = re.search(r"^run\(", tests, re.M)
            harness = tests + ("\nrun(__bench_model_ns__)\n" if wrapped and not invoked else "")
            f.write(code + "\n__bench_model_ns__ = dict(globals())\n" + harness + "\n")
        try:
            r = _run_grader([sys.executable, p], capture_output=True,
                               text=True, timeout=timeout, cwd=d)
        except subprocess.TimeoutExpired:
            return 0, total, "timeout"
        if r.returncode == 0:
            return total, total, "ok"
        err = (r.stderr or "").strip().splitlines()
        return 0, total, (err[-1][:160] if err else f"exit {r.returncode}")


def grade_markers(text, required, banned=()):
    """Partial credit: each required string that appears wins a check;
    any banned string zeroes the task. Deterministic, no judge."""
    t = (text or "").lower()
    for b in banned:
        if b.lower() in t:
            return 0, len(required), f"banned:{b[:40]}"
    hits = sum(1 for r in required if r.lower() in t)
    return hits, len(required), ("ok" if hits == len(required) else f"{hits}/{len(required)}")


def _materialise(kit, tmp):
    """kit is either {relpath: text} or {"__tree__": abs_dir} for fixtures that
    must keep binary/executable/git state."""
    if isinstance(kit, dict) and "__tree__" in kit:
        shutil.copytree(kit["__tree__"], tmp, dirs_exist_ok=True, symlinks=True)
        return
    for rel, content in (kit or {}).items():
        fp = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w") as f:
            f.write(content)


def grade_cmd(text, lang, kit, check, timeout=120, scratch=None, save_as=None):
    """Extract a fenced block (shell/python), materialise `kit` files in a
    scratch dir, run the model's block, then run `check`. End-state grading:
    we never look at the commands, only at whether the check passes."""
    code = block(text, lang) or block(text)
    if not code.strip():
        # tool-call-dialect models answer with agent tool calls, not fences
        code = agent_code(text)
    tmp = scratch or tempfile.mkdtemp(prefix="bench-")
    try:
        _materialise(kit, tmp)
        if not code.strip():
            return 0, 1, "no-code"
        if save_as:
            with open(os.path.join(tmp, save_as), "w") as f:
                f.write(code)
        elif lang == "python":
            run = [sys.executable, "-c", code]
        elif lang in ("bash", "sh"):
            sp = os.path.join(tmp, "_model.sh")
            with open(sp, "w") as f:
                f.write(code)
            run = ["bash", sp]
        else:
            return 0, 1, f"bad-lang:{lang}"
        if not save_as:
            try:
                r = _run_grader(run, capture_output=True, text=True,
                                   timeout=timeout, cwd=tmp)
            except subprocess.TimeoutExpired:
                return 0, 1, "model-timeout"
            if r.returncode != 0:
                err = (r.stderr or "").strip().splitlines()
                return 0, 1, f"model-exit{r.returncode}: " + (err[-1][:120] if err else "")
        # the check itself
        cp = os.path.join(tmp, "_check.py")
        with open(cp, "w") as f:
            f.write(check)
        try:
            c = _run_grader([sys.executable, cp], capture_output=True,
                               text=True, timeout=timeout, cwd=tmp)
        except subprocess.TimeoutExpired:
            return 0, 1, "check-timeout"
        if c.returncode == 0:
            return 1, 1, "ok"
        err = (c.stderr or "").strip().splitlines()
        return 0, 1, "check-fail: " + (err[-1][:160] if err else f"exit {c.returncode}")
    finally:
        if scratch is None:
            shutil.rmtree(tmp, ignore_errors=True)


def extract_files(text):
    """Full-file replacement contract: blocks tagged with a path.

    A block whose fence info starts with ``file`` (optionally followed by a
    path) is treated as the COMPLETE new content of that file::

        ```file dq/worker.py
        <entire new content>
        ```

    If the info tag carries no path, a leading ``# <path>`` marker line inside
    the block is used. Absolute paths are refused; ``..`` is refused. Returns
    {relpath: content} in first-seen order.
    """
    out = {}
    pat = r"```([A-Za-z0-9_+./ -]*)\s*\n(.*?)```"
    for m in re.finditer(pat, text or "", re.S):
        info = m.group(1).strip().lower()
        body = m.group(2)
        if not info.startswith("file"):
            continue
        rest = info[4:].strip()
        if rest and " " not in rest:
            path = rest
        else:
            # path may sit on the NEXT line ("```file\nrelpath\ncode") — the
            # way tool-call models emit file blocks (flash-next, 2026-09-23)
            lines = body.splitlines()
            first = lines[0].strip() if lines else ""
            if (
                first
                and " " not in first
                and not first.startswith("#")
                and ("/" in first or "." in first)
                and not first.endswith((";", ":"))
            ):
                path = first
                body = "\n".join(lines[1:]).lstrip("\n")
            elif lines and lines[0].lstrip().startswith("# "):
                path = lines[0].lstrip()[2:].strip()
                body = "\n".join(lines[1:]).lstrip("\n")
            else:
                continue
        path = path.lstrip("./")
        if not path or path.startswith(("..", "/")):
            continue
        # an EMPTY block must not clobber the kit file: it usually means the
        # model showed an unchanged file as a stub (2026-09-23 pilot: qwen
        # emptied pynq/__init__.py and broke the import of an otherwise
        # correct d4-retry-backoff answer)
        if not body.strip():
            continue
        out.setdefault(path, body)
    return out


def grade_files(text, kit, check, timeout=180):
    """DeepSWE with the full-file contract: the model writes COMPLETE new
    contents for every changed file, one ```file <path> block each. We
    materialise the kit, overwrite those paths, then run the repo's verifier.
    End-state grading — any implementation that provides the behaviour passes.
    This is the contract real agents use (write files, not hunks); the diff
    contract graded every model 0 because patch rejects their output."""
    files = extract_files(text)
    if not files:
        return 0, 1, "no-file-blocks"
    tmp = tempfile.mkdtemp(prefix="bench-repo-")
    try:
        _materialise(kit, tmp)
        for rel, content in files.items():
            fp = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w") as f:
                f.write(content)
        cp = os.path.join(tmp, "_check.py")
        with open(cp, "w") as f:
            f.write(check)
        try:
            c = _run_grader([sys.executable, cp], capture_output=True,
                               text=True, timeout=timeout, cwd=tmp)
        except subprocess.TimeoutExpired:
            return 0, 1, "check-timeout"
        if c.returncode == 0:
            return 1, 1, "ok"
        err = (c.stderr or "").strip().splitlines()
        return 0, 1, "check-fail: " + (err[-1][:160] if err else f"exit {c.returncode}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def grade_diff(text, kit, check, timeout=180, patch_cmd=("patch", "-p1", "-f", "--no-backup-if-mismatch")):
    """DeepSWE/SWE-bench shape: the model returns a unified diff, we materialise
    the repo, apply the diff, then run the repo's own verifier. End-state grading
    — an alternative-but-correct implementation passes, the commands don't matter."""
    d = extract_diff(text)
    if not d.strip():
        return 0, 1, "no-diff"
    tmp = tempfile.mkdtemp(prefix="bench-repo-")
    try:
        _materialise(kit, tmp)
        dp = os.path.join(tmp, "_model.patch")
        with open(dp, "w") as f:
            f.write(d if d.endswith("\n") else d + "\n")
        r = _run_grader(list(patch_cmd) + ["-i", dp], capture_output=True,
                           text=True, timeout=60, cwd=tmp)
        if r.returncode != 0:
            r2 = _run_grader(["git", "apply", "-p1", "--unsafe-paths", dp],
                                capture_output=True, text=True, timeout=60, cwd=tmp)
            if r2.returncode != 0:
                err = (r.stderr or r2.stderr or "").strip().splitlines()
                return 0, 1, "patch-failed: " + (err[-1][:120] if err else "")
        cp = os.path.join(tmp, "_check.py")
        with open(cp, "w") as f:
            f.write(check)
        try:
            c = _run_grader([sys.executable, cp], capture_output=True,
                               text=True, timeout=timeout, cwd=tmp)
        except subprocess.TimeoutExpired:
            return 0, 1, "check-timeout"
        if c.returncode == 0:
            return 1, 1, "ok"
        err = (c.stderr or "").strip().splitlines()
        return 0, 1, "check-fail: " + (err[-1][:160] if err else f"exit {c.returncode}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def extract_diff(text):
    """Fenced ```diff block, else the longest run of lines that looks like a
    unified diff (some models paste it bare)."""
    for lang in ("diff", "patch"):
        b = block(text, lang)
        if b.strip():
            return b
    lines = (text or "").splitlines()
    keep, cur = [], []
    for ln in lines:
        if ln.startswith(("diff --git", "--- ", "+++ ", "@@", "+", "-", " ")) and ln.strip() != "":
            cur.append(ln)
        else:
            if len(cur) > len(keep):
                keep = cur
            cur = []
    if len(cur) > len(keep):
        keep = cur
    return "\n".join(keep)


# ---------------------------------------------------------------- packs
def load_pack(name):
    d = os.path.join(PACKS, name)
    f = os.path.join(d, "pack.json") if os.path.exists(os.path.join(d, "pack.json")) \
        else os.path.join(d, "tasks.json")
    with open(f) as fh:
        p = json.load(fh)
    if isinstance(p, list):
        p = {"name": name, "tasks": p}
    p.setdefault("name", name)
    if p.get("corpus"):
        with open(os.path.join(d, p["corpus"])) as cf:
            p["_corpus_text"] = cf.read()
    if p.get("refs"):
        tasks = []
        for ref in p["refs"]:
            pname, tid = ref.split("/", 1)
            src = load_pack(pname)
            hit = [t for t in src["tasks"] if t["id"] == tid]
            if not hit:
                raise SystemExit(f"triage ref not found: {ref}")
            for t in hit:
                t = dict(t)
                t["domain"] = src.get("domain", pname)
                t["id"] = f"{pname}:{t['id']}"
                tasks.append(t)
        p["tasks"] = tasks
        p.setdefault("system", None)
    for t in p.get("tasks", []):
        t.setdefault("domain", name)
        if p.get("_corpus_text") and "corpus_text" not in t:
            t["corpus_text"] = p["_corpus_text"]
        if p.get("system"):
            t.setdefault("system", p["system"])
        t.setdefault("weight", 1)
        if "corpus" in t and "corpus_text" not in t:
            cp = t["corpus"]
            if not os.path.isabs(cp):
                with open(os.path.join(d, cp)) as cf:
                    t["corpus_text"] = cf.read()
        # refs already resolved kit/corpus_text in the source pack dir; only
        # resolve here when the task still needs it (non-ref) — otherwise a
        # ref'd terminal kit_tree gets re-pointed at THIS pack's dir and crashes
        if "kit_tree" in t and "kit" not in t:
            t["kit"] = {"__tree__": os.path.join(d, t["kit_tree"])}
        if "kit_dir" in t and "kit" not in t:
            base = os.path.join(d, t["kit_dir"])
            kit = {}
            for rel in t.get("kit_files", []):
                with open(os.path.join(base, rel)) as kf:
                    kit[rel] = kf.read()
            t["kit"] = kit
    return p


def mark(ok, total):
    return "PASS" if ok == total and total else ("PART" if ok else "FAIL")