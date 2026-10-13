#!/usr/bin/env python3
"""Run the approved comparison, leaving Ornith inactive."""
import datetime
import hashlib
import json
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from bench_contract_v2 import load_contract_v2_pack
import importlib.util
spec = importlib.util.spec_from_file_location('benchmark_runner', ROOT / 'bench-run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def command(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def health(port, model, deadline=900):
    start = time.monotonic()
    while time.monotonic() - start < deadline:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=3) as response:
                models = json.load(response)['data']
            if any(x['id'] == model for x in models):
                return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(3)
    raise RuntimeError(f'Model {model} failed readiness on {port}')


def verify_medium(port, lane):
    records = {}
    for effort in ('medium', 'xhigh'):
        body = {'messages': [{'role':'user','content':'Reply ready'}], 'chat_template_kwargs': {'reasoning_effort':effort}, 'add_generation_prompt':True}
        route = '/apply-template' if lane == 'qwen27b' else '/tokenize'
        req = urllib.request.Request(f'http://127.0.0.1:{port}{route}', data=json.dumps(body).encode(), headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            records[effort] = json.load(response)
    if lane == 'qwen27b':
        assert 'Reasoning effort is set to xhigh' not in records['medium']['prompt']
        assert 'Reasoning effort is set to xhigh' in records['xhigh']['prompt']
    else:
        assert records['medium']['count'] < records['xhigh']['count']
    return records


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    prefix = sys.argv[1] if len(sys.argv)>1 else f'qwen27b-flash-matched-{stamp}'
    if '/' in prefix or not prefix.startswith('qwen27b-flash-matched-'):
        raise ValueError('Invalid campaign prefix')
    results = ROOT / 'results'
    plan = json.loads((results / 'qwen27b-flash-matched-launch-plan.json').read_text())
    active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'llama-ornith.service']).returncode == 0
    manifest = dict(plan, prefix=prefix, created=datetime.datetime.now(datetime.timezone.utc).isoformat(), status='running', originally_active=active)
    manifest.pop('qwen_environment', None)
    manifest.update(runs_per_model=3, restore_on_exit=False)
    tasks = load_contract_v2_pack('deepswe2')['tasks']
    manifest['tasks'] = {t['id']: {'task_sha256': hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest(),
                               'message_sha256': hashlib.sha256(json.dumps(runner.build_messages(t, True), sort_keys=True).encode()).hexdigest(),
                               'initial_cap': t.get('max_tokens'), 'escalate': t.get('escalate')} for t in tasks}
    manifest['file_sha256'] = {f: sha(ROOT / f) for f in ['bench-run.py', 'bench_lib.py', 'tools/bench_contract_v2.py', 'tools/bench_corrected_suite.py']}
    paths = [Path(plan['qwen_command'][2]), *Path(plan['flash_config']['model']).parent.glob('*.gguf')]
    manifest['model_files'] = {str(p): {'size': p.stat().st_size, 'mtime_ns': p.stat().st_mtime_ns} for p in paths}
    manifest['engine_version'] = subprocess.run(['/usr/bin/llama-server','--version'],capture_output=True,text=True).stderr
    manifest['campaigns'] = []
    destination = results / f'{prefix}.manifest.json'

    if destination.exists():
        previous = json.loads(destination.read_text())
        for key in ('tasks', 'file_sha256', 'qwen_command', 'flash_config', 'model_files'):
            if previous.get(key) != manifest.get(key):
                raise ValueError('Resume manifest mismatch: '+key)
        manifest = previous
        manifest['status'] = 'running'

    def save():
        destination.write_text(json.dumps(manifest, indent=2) + '\n')

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f'Interrupted by signal {signum}')

    signal.signal(signal.SIGTERM, interrupted)
    save()
    units = []
    start = time.monotonic()
    try:
        # Refuse to interrupt an unrelated inference workload.
        procs = subprocess.run(['pgrep', '-x', 'llama-server'], capture_output=True, text=True).stdout.split()
        ornith_pid = subprocess.check_output(['systemctl', '--user', 'show', 'llama-ornith.service', '-p', 'MainPID', '--value'], text=True).strip()
        # The existing dedicated embedding server is outside the scored lane.
        foreign = []
        for pid in procs:
            if pid == ornith_pid:
                continue
            argv = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
            if b'--embeddings' not in argv:
                foreign.append(pid)
        if foreign:
            raise RuntimeError('Unexpected llama-server process; inspect before starting')
        if active:
            command(['systemctl', '--user', 'stop', 'llama-ornith.service'])
        time.sleep(3)
        lanes = [('qwen27b', 'matched-qwen27b-medium', 18080, 'matched-qwen38-27b-q5', plan['qwen_command']),
                 ('flash', 'matched-strata-iq3-medium', 18081, 'qwen3.8-flash-next-iq3_xxs',
                  ['/usr/bin/python3', '/home/USER/opt/UnbiasedStrata/local/launch.py', '--config', str(results / 'qwen27b-flash-matched-strata-config.json')])]
        order = [(0,40),(1,40),(1,41),(0,41),(0,42),(1,42)]
        for index, seed in order:
            lane, target, port, model, launch = lanes[index]
            tag = f'{prefix}-{lane}-{seed}'
            recorded = next((c for c in manifest['campaigns'] if c['tag']==tag), None)
            if recorded and recorded.get('rows')==24:
                continue
            unit = f'bench-matched-{lane}-{seed}-{stamp}'
            units.append(unit)
            command(['systemd-run', '--user', '--unit', unit, '--property=KillMode=control-group', '--property=TimeoutStopSec=30', '/usr/bin/env', '-u', 'GGML_VK_VISIBLE_DEVICES', *launch])
            health(port, model)
            medium_verification = verify_medium(port, lane)
            pid = subprocess.check_output(['systemctl','--user','show',unit,'-p','MainPID','--value'],text=True).strip()
            actual = Path(f'/proc/{pid}/cmdline').read_bytes().decode().split('\0')[:-1]
            exe = Path(f'/proc/{pid}/exe').resolve()
            tag = f'{prefix}-{lane}-{seed}'
            entry = {'lane': lane, 'target': target, 'tag': tag, 'served_model': model, 'command': launch, 'seed': seed, 'medium_verification': medium_verification, 'actual_argv': actual, 'engine': str(exe), 'engine_sha256': sha(exe)}
            if any(c['lane']==lane and c.get('engine_sha256')!=entry['engine_sha256'] for c in manifest['campaigns']):
                raise RuntimeError('Engine executable changed; refusing to score resumed campaign')
            manifest['campaigns'] = [c for c in manifest['campaigns'] if c['tag']!=tag]+[entry]
            save()
            with (results / f'{tag}.log').open('w') as log:
                command([sys.executable, '-u', str(ROOT / 'bench-run.py'), '--targets', target, '--packs', 'deepswe2', '--tag', tag,
                         '--seed', str(seed), '--thinking', 'medium', '--suite-version', 'contract-v2', '--include-fixtures', '--resume'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            doc = json.loads((results / f'{tag}.json').read_text())
            rows = doc['targets'][target]['rows']
            if len(rows) != 24 or {r['task'] for r in rows} != {t['id'] for t in tasks}:
                raise RuntimeError(f'Incomplete campaign {tag}')
            entry.update(rows=24, passes=sum(r['status'] == 'pass' for r in rows),
                         hard_passes=sum(r['status'] == 'pass' for r in rows if r['tier'] == 't4'),
                         median_latency_s=statistics.median(r['wall_s'] for r in rows),
                         median_decode_ts=statistics.median(r['decode_ts'] for r in rows if r.get('decode_ts')),
                         wall_s=doc['targets'][target]['wall_s'])
            save()
            command(['systemctl', '--user', 'stop', unit])
            time.sleep(3)
        manifest['status'] = 'inference_complete'
        save()
        campaigns = manifest['campaigns']
        command([sys.executable, str(ROOT / 'tools' / 'matched_analysis.py'), str(destination)])
        manifest['status'] = 'complete'
        return
    except BaseException as exc:
        manifest['status'] = 'failed'
        manifest['error'] = repr(exc)
        raise
    finally:
        for unit in units:
            subprocess.run(['systemctl', '--user', 'stop', unit], check=False)
        manifest['ornith_restart_requested'] = False
        manifest['elapsed_s'] = round(time.monotonic() - start, 1)
        save()
        print(destination, flush=True)


if __name__ == '__main__':
    main()
