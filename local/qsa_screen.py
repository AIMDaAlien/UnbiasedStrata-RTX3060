#!/usr/bin/python3
"""Bounded preliminary QSA screen. Never edits the production configuration."""
import argparse
import copy
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time

from launch import CONFIG, ROOT, optimization_environment
from long_context import CHECKPOINTS, run
from paired_report import evaluate

FIXTURES = ROOT / 'local/benchmarks/long-20261010-v4/fixtures'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def save(path, record):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n')
    temporary.replace(path)


def capacity_halves(path):
    size = path.stat().st_size
    if not size or size % 2:
        return False
    halves = []
    with path.open('rb') as f:
        for _ in range(2):
            h = hashlib.sha256()
            remaining = size // 2
            while remaining:
                chunk = f.read(min(1024 * 1024, remaining))
                h.update(chunk)
                remaining -= len(chunk)
            halves.append(h.hexdigest())
    return halves[0] == halves[1]


def profile_summary(record, output):
    summaries = []
    for r in record['runs']:
        phases = {}
        timeline = 0
        for line in r['prefill_diagnostics']:
            if 'GPU timeline' not in line:
                continue
            timeline += float(re.search(r'GPU timeline ([\d.]+) ms', line)[1])
            for name, value in re.findall(r' ([a-z/+ ]+?) ([\d.]+) \([\d.]+%\)', line.split('ms:', 1)[1]):
                phases[name.strip()] = phases.get(name.strip(), 0) + float(value)
        t = r['timings']
        if not {'qsa select', 'qsa attn', 'gemm gate/up', 'kv stage'} <= phases.keys():
            raise RuntimeError('profiling categories missing; cannot assess the selection threshold')
        if timeline <= 0 or t.get('prompt_ms', 0) <= 0:
            raise RuntimeError('invalid profiled prefill duration')
        summaries.append({
            'target_tokens': r['target_tokens'], 'checks': r['checks'],
            'total_response_seconds': r['wall_seconds'],
            'prefill_seconds': t.get('prompt_ms', 0) / 1000,
            'decode_seconds': t.get('predicted_ms', 0) / 1000,
            'qsa_selection_ms': phases.get('qsa select', 0),
            'qsa_attention_ms': phases.get('qsa attn', 0),
            'expert_compute_ms': sum(phases.get(k, 0) for k in ('gemm gate/up', 'gemm down')),
            'expert_compute_note': 'Fused experts charge gate/up and down together to gemm gate/up; unfused adds gemm down.',
            'kv_staging_ms': phases.get('kv stage', 0),
            'gpu_timeline_ms': timeline, 'phases_ms': phases,
            'selection_share_of_profiled_prefill': phases['qsa select'] / t['prompt_ms'],
            'selection_share_of_gpu_timeline': phases['qsa select'] / timeline,
        })
    text = (output / 'engine.log').read_text(errors='replace')
    return {'status': record['status'], 'requests': summaries,
            'dispatch': [l for l in text.splitlines() if 'strata topk dispatch:' in l]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--baseline-profile', type=Path, default=CONFIG)
    ap.add_argument('--build', required=True, type=Path)
    ap.add_argument('--deadline', required=True, help='ISO UTC deadline')
    a = ap.parse_args()
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    build = a.build.resolve()
    lock = open(ROOT / 'local/long-context.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    deadline = datetime.datetime.fromisoformat(a.deadline).timestamp()
    remaining = deadline - time.time()
    if remaining <= 0:
        raise RuntimeError('deadline already reached')
    def emergency_stop():
        units = subprocess.check_output(['systemctl', '--user', 'list-units',
            '--all', '--plain', '--no-legend', f'unbiasedstrata-long-{os.getpid()}-*'], text=True)
        for line in units.splitlines():
            subprocess.run(['systemctl', '--user', 'stop', line.split()[0]], timeout=35, check=False)
    def deadline_stop():
        print('Deadline reached; interrupting and preserving incomplete evidence.', flush=True)
        escalation = threading.Timer(40, emergency_stop)
        escalation.daemon = True
        escalation.start()
        os.kill(os.getpid(), signal.SIGINT)
    timer = threading.Timer(remaining, deadline_stop)
    timer.daemon = True
    timer.start()
    state = {'status': 'in_progress', 'preliminary': True, 'production_changed': False,
             'deadline_utc': a.deadline, 'completed': [], 'exclusions': [],
             'morning_next_step': 'Review screening; await explicit continue before further testing.'}
    fixture_hashes = {p.name: sha(p) for p in sorted(FIXTURES.glob('*.json'))}
    expected = {'fresh-' + str(n) + '.json' for n in CHECKPOINTS}
    growing = sorted(set(list(range(8192, 180000, 8192)) + list(CHECKPOINTS)))
    expected |= {'growing-' + str(n) + suffix for n in growing for suffix in ('.json', '.tool.json')}
    if not expected <= fixture_hashes.keys():
        raise RuntimeError('canonical intermediate/tool fixtures missing')
    base = json.loads(a.baseline_profile.read_text())
    base.update(context=196608, port=18081, binary=str(build / 'unbiased-strata'))
    for k in ('amd_helper', 'amd_device', 'amd_vram_mib', 'amd_decode_only'):
        base.pop(k, None)
    env = optimization_environment(base)
    diagnostics = {k for k in env if 'TIMING' in k or k.startswith('STRATA_TOPK_')}
    diagnostics |= {'STRATA_TOPK_OLD', 'STRATA_TOPK_CAPACITY_GUARD', 'STRATA_TOPK_TRACE',
                    'STRATA_PREFILL_TIMING', 'STRATA_PF_FUSED_TILE', 'STRATA_QSA_CLUSTER', 'STRATA_QSA_WARP'}
    env.update({k: None for k in diagnostics})
    env.update(STRATA_PF_FUSED='1', STRATA_PREFILL_AUTO_MAX='16384', STRATA_PREFILL_RING='512')
    base['environment'] = env
    profiles = {name: dict(base, environment=dict(env, STRATA_TOPK_ACTIVE_ANY=str(active)))
                for name, active in [('control', 0), ('treatment', 1)]}
    for name, p in profiles.items():
        save(output / (name + '.json'), p)
    cap = float(subprocess.check_output(['nvidia-smi', '--id=0', '--query-gpu=power.limit',
                                        '--format=csv,noheader,nounits'], text=True).strip())
    if cap != 100:
        raise RuntimeError('existing 100 W GPU power limit required')
    manifest = {'profiles': profiles, 'effective_environment': {k: optimization_environment(p) for k,p in profiles.items()},
                'fixture_sha256': fixture_hashes, 'production_profile_sha256': sha(CONFIG),
                'binary_sha256': sha(build / 'unbiased-strata'), 'parity_binary_sha256': sha(build / 'qsa_topk_active_parity'),
                'memory_max_bytes': 56 * 1024**3, 'memory_swap_max_bytes': 0,
                'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}
    save(output / 'manifest.json', manifest)
    (output / 'source.diff').write_text(subprocess.check_output(['git', 'diff'], cwd=ROOT, text=True))
    save(output / 'state.json', state)
    try:
        parity = {}
        for name, p in profiles.items():
            dest = output / (name + '-selected-ids.bin')
            with (output / (name + '-parity.log')).open('w') as log:
                clean_env = {k:v for k,v in os.environ.items() if not k.startswith('STRATA_')}
                clean_env.update(optimization_environment(p))
                child = subprocess.Popen([str(build / 'qsa_topk_active_parity'), str(dest)],
                    env=clean_env, stdout=log, stderr=subprocess.STDOUT)
                try:
                    code = child.wait(timeout=max(1, deadline-time.time()))
                finally:
                    if child.poll() is None:
                        child.terminate()
                        try:
                            child.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            child.wait()
            parity[name] = {'exit_code': code, 'selected_ids_sha256': sha(dest) if dest.exists() else None,
                            'capacities_selected_ids_identical': capacity_halves(dest) if code == 0 else False}
            if code != 0 or not parity[name]['capacities_selected_ids_identical']:
                save(output / 'parity.json', parity)
                raise RuntimeError('parity failed; performance testing stopped')
        if parity['control']['selected_ids_sha256'] != parity['treatment']['selected_ids_sha256']:
            save(output / 'parity.json', parity)
            raise RuntimeError('control/treatment selected-ID mismatch; performance testing stopped')
        parity['status'] = 'passed'
        save(output / 'parity.json', parity)
        state['completed'].append('104 parity cases each with actual control=0 and treatment=1; identical selected IDs')
        save(output / 'state.json', state)
        profiled = {}
        for name, p in profiles.items():
            path = output / 'profile' / name
            if (path / 'results.json').exists():
                raise RuntimeError('use a fresh output directory; existing run evidence preserved')
            instrumented = copy.deepcopy(p)
            instrumented['environment'].update(STRATA_PREFILL_TIMING='1', STRATA_TOPK_TRACE='1')
            r = run(instrumented, (128000, 180000), ('fresh',), path, FIXTURES)
            profiled[name] = profile_summary(r, path)
            save(output / 'profile-summary.json', profiled)
            if r['status'] != 'passed':
                raise RuntimeError('profile quality failure; rejected for rollout')
            dispatch = profiled[name]['dispatch']
            if name == 'treatment' and not any('counted=1' in l and 'kernel=register' in l for l in dispatch):
                raise RuntimeError('active-bound register dispatch was not observed')
            if name == 'control' and any('counted=1' in l for l in dispatch):
                raise RuntimeError('control unexpectedly used active-bound dispatch')
            state['completed'].append(name + ' fresh128K/180K profiled and quality passed; dispatch verified')
            save(output / 'state.json', state)
        pair = {}
        for name, p in profiles.items():
            path = output / 'paired' / '0' / name
            pair[name] = run(p, CHECKPOINTS, ('fresh', 'growing'), path, FIXTURES)
            if pair[name]['status'] != 'passed':
                raise RuntimeError('paired quality failure; incomplete pair excluded from speed results')
            state['completed'].append(name + ' six-bucket uninstrumented run, including intermediate turns and tools')
            save(output / 'state.json', state)
        report = evaluate([(pair['control'], pair['treatment'])], treatment_fields=('environment',))
        ratio = report.pop('amd_on_off_geomean_ratio')
        report.pop('eligible_to_enable', None)  # the generic evaluator's AMD rollout gate is unrelated
        report.update(treatment_control_geomean_ratio=ratio, preliminary=True,
                      promising=ratio <= .98 and max(report['bucket_ratios'].values()) <= 1.05,
                      rollout_approved=False, confidence_interval=None,
                      actual_treatment_environment=['STRATA_TOPK_ACTIVE_ANY'],
                      minimum_geomean_improvement_percent=2, maximum_bucket_slowdown_percent=5,
                      profiling_excluded_from_speed_results=True)
        report['screening_decision'] = 'promising' if report['promising'] else 'rejected for rollout'
        save(output / 'decision.json', report)
        state['status'] = 'completed'
        state['screening_decision'] = report['screening_decision']
        state['morning_next_step'] = ('Await continue, then run five alternating acceptance pairs.' if report['promising']
            else 'Setting rejected for rollout; await continue before any further investigation.')
    except (KeyboardInterrupt, subprocess.TimeoutExpired):
        state['status'] = 'incomplete'
        state['exclusions'].append('two-hour deadline or interruption; unfinished runs excluded from speed results')
        for path in output.glob('**/results.json'):
            r = json.loads(path.read_text())
            if r['status'] != 'passed':
                r['status'] = 'incomplete'
                r['speed_results_excluded'] = True
                save(path, r)
    except Exception as e:
        state['status'] = 'failed'
        state['exclusions'].append(str(e))
        print(str(e), flush=True)
    finally:
        timer.cancel()
        emergency_stop()
        current = {p.name: sha(p) for p in sorted(FIXTURES.glob('*.json'))}
        state['fixtures_unchanged'] = current == fixture_hashes
        state['production_profile_unchanged'] = sha(CONFIG) == manifest['production_profile_sha256']
        state['ended_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(output / 'state.json', state)
        print(json.dumps(state), flush=True)


if __name__ == '__main__':
    main()
