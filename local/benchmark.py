#!/usr/bin/python3
"""Measure CPU-thread/MTP settings with GPU telemetry; optionally save the winner."""
import argparse
import itertools
import json
import os
from pathlib import Path
import statistics
import subprocess
import threading
import time
import urllib.error
import urllib.request

from launch import CONFIG, ROOT, command, optimization_environment

BASE = 'http://127.0.0.1:18081'


def request(path, body=None, timeout=5):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def processes(pid):
    result = [pid]
    try:
        children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
    except OSError:
        return result
    for child in children:
        result.extend(processes(int(child)))
    return result


def cpu_seconds(pid):
    total = 0
    for process in processes(pid):
        try:
            fields = Path(f'/proc/{process}/stat').read_text().rsplit(')', 1)[1].split()
            total += int(fields[11]) + int(fields[12])
        except (OSError, ValueError, IndexError):
            pass
    return total / os.sysconf('SC_CLK_TCK')


def monitor(stop, samples):
    while not stop.is_set():
        try:
            output = subprocess.check_output([
                'nvidia-smi', '--id=0',
                '--query-gpu=utilization.gpu,utilization.memory,power.draw,memory.used',
                '--format=csv,noheader,nounits'], text=True, timeout=5)
            gpu, memory, watts, vram = map(float, output.strip().split(','))
            samples.append({'time': time.time(), 'gpu_percent': gpu,
                            'memory_controller_percent': memory, 'watts': watts,
                            'vram_mib': vram})
        except (subprocess.SubprocessError, ValueError):
            pass
        stop.wait(0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='also test two-token MTP drafts')
    parser.add_argument('--apply', action='store_true', help='save measured winning threads/spec')
    parser.add_argument('--repeats', type=int, default=2)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    subprocess.run(['nvidia-smi', '--id=0'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['systemctl', '--user', 'show-environment'], check=True,
                   stdout=subprocess.DEVNULL)
    try:
        request('/health')
    except urllib.error.URLError:
        pass
    else:
        parser.error('port 18081 is already in use')
    if subprocess.run(['systemctl', '--user', 'is-active', '--quiet',
                       'unbiasedstrata.service']).returncode == 0:
        parser.error('stop unbiasedstrata.service first so two model copies do not compete for RAM/VRAM')
    free_vram = int(subprocess.check_output([
        'nvidia-smi', '--id=0', '--query-gpu=memory.free', '--format=csv,noheader,nounits'], text=True))
    if free_vram < 10000:
        parser.error('the 3060 has less than 10000 MiB free; stop other inference workloads first')
    config = json.loads(CONFIG.read_text())
    output = ROOT / 'local' / 'benchmarks' / time.strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True)
    runs = []
    variants = list(itertools.product([8, 12, 15, 16], [4, 2] if args.full else [4]))
    for threads, spec in variants:
        profile = dict(config, threads=threads, spec=spec, port=18081)
        unit = f'unbiasedstrata-bench-{os.getpid()}-{threads}-{spec}'
        log = output / f'{threads}threads-{spec}draft.log'
        env = optimization_environment(profile)
        envargs = [f'{k}={v}' for k, v in sorted(env.items())]
        print(f'Loading threads={threads}, spec={spec}...', flush=True)
        subprocess.run(['systemd-run', '--user', '--collect', f'--unit={unit}',
                        '--property=MemoryMax=56G',
                        '--property=MemorySwapMax=0',
                        '--property=TimeoutStopSec=30', '--property=KillMode=control-group',
                        f'--property=StandardOutput=append:{log}',
                        f'--property=StandardError=append:{log}',
                        '/usr/bin/env', *envargs, *command(profile)], check=True)
        try:
            deadline = time.monotonic() + 900
            while True:
                try:
                    request('/health')
                    break
                except urllib.error.URLError:
                    pass
                state = subprocess.check_output(
                    ['systemctl', '--user', 'show', unit, '--property=ActiveState', '--value'],
                    text=True).strip()
                if state not in ('active', 'activating') or time.monotonic() > deadline:
                    raise RuntimeError(f'{unit} did not become ready; see {log}')
                time.sleep(2)
            pid = int(subprocess.check_output(
                ['systemctl', '--user', 'show', unit, '--property=MainPID', '--value'], text=True))
            # Warm-up is excluded. Unique text near the start prevents prefix-cache reuse.
            request('/v1/chat/completions', {
                'messages': [{'role': 'user', 'content': 'Reply with the word ready.'}],
                'max_tokens': 16, 'reasoning_effort': 'none'}, timeout=900)
            measurements = []
            for repeat, size in itertools.product(range(args.repeats), [0, 80]):
                prompt = f'Case {threads}-{spec}-{repeat}-{size}. Read these design notes.\n'
                prompt += ('A worker must batch transfers, bound queues, and preserve result ordering. '
                           'Measure waiting separately from computation and test cancellation.\n') * size
                prompt += ('Write 100 numbered, detailed implementation steps for a Python worker pool '
                           'with bounded queues and ordered results. Continue until all steps are complete.')
                samples, stop = [], threading.Event()
                worker = threading.Thread(target=monitor, args=(stop, samples), daemon=True)
                worker.start()
                start_cpu, started = cpu_seconds(pid), time.monotonic()
                try:
                    result = request('/v1/chat/completions', {
                        'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0,
                        'reasoning_effort': 'none', 'max_tokens': 512}, timeout=1800)
                finally:
                    elapsed = time.monotonic() - started
                    cores = (cpu_seconds(pid) - start_cpu) / elapsed
                    stop.set()
                    worker.join(timeout=6)
                if 'error' in result:
                    raise RuntimeError(result['error'])
                tokens = result['usage']['completion_tokens']
                if tokens < 128:
                    raise RuntimeError('generation too short to compare reliably; inspect response')
                timing = result.get('timings', {})
                measurements.append({'repeat': repeat, 'prompt_size': size,
                    'wall_seconds': elapsed, 'completion_tokens': tokens,
                    'end_to_end_tokens_per_second': tokens / elapsed,
                    'timings': timing, 'mean_cpu_cores_busy': cores, 'gpu_samples': samples,
                    'mean_gpu_percent': statistics.mean(s['gpu_percent'] for s in samples) if samples else None,
                    'mean_watts': statistics.mean(s['watts'] for s in samples) if samples else None})
                print(f'  {tokens / elapsed:.2f} output tokens/s incl. prompt; '
                      f'{cores:.1f} CPU cores busy; timings={timing}', flush=True)
            run = {'profile': profile, 'environment': env, 'measurements': measurements,
                   'mean_wall_seconds': statistics.mean(m['wall_seconds'] for m in measurements),
                   'seconds_per_output_token': sum(m['wall_seconds'] for m in measurements) /
                                               sum(m['completion_tokens'] for m in measurements)}
            runs.append(run)
            (output / 'results.json').write_text(json.dumps(runs, indent=2) + '\n')
        finally:
            subprocess.run(['systemctl', '--user', 'stop', unit], check=False)
    winner = min(runs, key=lambda r: r['seconds_per_output_token'])
    print('Best measured profile:', json.dumps(winner['profile']), flush=True)
    print('Evidence:', output / 'results.json', flush=True)
    if args.apply:
        backup = CONFIG.with_name('config.json.before-benchmark-' + time.strftime('%Y%m%d-%H%M%S'))
        backup.write_text(CONFIG.read_text())
        config.update({k: winner['profile'][k] for k in ['threads', 'spec']})
        temp = CONFIG.with_suffix('.tmp')
        temp.write_text(json.dumps(config, indent=2) + '\n')
        temp.replace(CONFIG)
        print('Saved winner. Start unbiasedstrata.service to use it.', flush=True)


if __name__ == '__main__':
    main()
