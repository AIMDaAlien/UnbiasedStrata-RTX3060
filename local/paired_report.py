#!/usr/bin/python3
"""Evaluate five paired local results against the rollout gates. Does not enable AMD."""
import argparse
import json
import math
from pathlib import Path
import statistics

BUCKETS = [(w, n) for w in ('fresh', 'growing') for n in (80000, 128000, 180000)]

def buckets(record):
    if record['status'] != 'passed':
        raise ValueError('failed or incomplete profile cannot be counted as a speedup')
    result = {}
    for run in record['runs']:
        key = run['workload'], run['target_tokens']
        if key not in BUCKETS:
            continue
        if not all(run['checks'].values()) or run['finish_reason'] != 'stop':
            raise ValueError('quality or generation completion failed')
        if key in result:
            raise ValueError('duplicate workload bucket')
        for metric in ('wall_seconds', 'conversation_wall_seconds'):
            if not math.isfinite(run[metric]) or run[metric] <= 0:
                raise ValueError('invalid wall-time measurement')
        result[key] = run
    if set(result) != set(BUCKETS):
        raise ValueError('all six workload buckets are required')
    return result

def evaluate(pairs, treatment_fields=('environment', 'amd_helper', 'amd_device',
                                     'amd_vram_mib', 'amd_decode_only')):
    ratios = {b: [] for b in BUCKETS}
    repetitions = []
    for off, on in pairs:
        if off['profile'] != pairs[0][0]['profile'] or on['profile'] != pairs[0][1]['profile']:
            raise ValueError('configuration changed between paired repetitions')
        if off.get('launch', {}).get('binary_sha256') != pairs[0][0].get('launch', {}).get('binary_sha256'):
            raise ValueError('binary changed between paired repetitions')
        for field in set(off['profile']) | set(on['profile']):
            if field not in treatment_fields and off['profile'].get(field) != on['profile'].get(field):
                raise ValueError('undeclared paired treatment: ' + field)
        for field in ('context', 'kv', 'kv_resident', 'model', 'pack', 'mtp'):
            if off['profile'].get(field, 0) != on['profile'].get(field, 0):
                raise ValueError('paired configuration mismatch: ' + field)
        if off.get('launch', {}).get('binary_sha256') != on.get('launch', {}).get('binary_sha256'):
            raise ValueError('paired binaries differ')
        ae, be = off.get('environment', {}), on.get('environment', {})
        ap, bp = off['profile'].get('environment', {}), on['profile'].get('environment', {})
        declared = {k for k in set(ap) | set(bp) if ap.get(k) != bp.get(k)}
        actual = {k for k in set(ae) | set(be) if ae.get(k) != be.get(k)}
        if not actual <= declared:
            raise ValueError('undeclared optimization environment difference')
        a, b = buckets(off), buckets(on)
        logs = []
        for bucket in BUCKETS:
            if a[bucket]['fixture_sha256'] != b[bucket]['fixture_sha256']:
                raise ValueError('paired fixtures differ')
            metric = 'conversation_wall_seconds' if bucket[0] == 'growing' else 'wall_seconds'
            ratio = b[bucket][metric] / a[bucket][metric]
            ratios[bucket].append(ratio)
            logs.append(math.log(ratio))
        repetitions.append(statistics.mean(logs))
    mean = statistics.mean(repetitions)
    ci = None
    if len(repetitions) == 5:
        # Paired t interval on the repetition's log geometric mean, df=4.
        half = 2.776445105 * statistics.stdev(repetitions) / math.sqrt(5)
        ci = [math.exp(mean-half), math.exp(mean+half)]
    bucket_ratios = {f'{w}-{n}': math.exp(statistics.mean(math.log(r) for r in rs))
                     for (w,n),rs in ratios.items()}
    overall = math.exp(mean)
    return {'paired_repetitions': len(pairs), 'amd_on_off_geomean_ratio': overall,
            'declared_treatment_fields': list(treatment_fields),
            'wall_time_improvement_percent': 100*(1-overall), 'paired_95_ci_ratio': ci,
            'bucket_ratios': bucket_ratios,
            'eligible_to_enable': len(pairs) == 5 and overall <= 0.9 and ci[1] < 1
                                  and max(bucket_ratios.values()) <= 1.05}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', nargs=2, type=Path, action='append', required=True,
                        metavar=('OFF_RESULTS', 'ON_RESULTS'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--treatment-field', action='append', default=[],
                        choices=('threads', 'spec', 'ple_io'),
                        help='explicitly allow an additional optimization setting to differ')
    args = parser.parse_args()
    report = evaluate([(json.loads(a.read_text()), json.loads(b.read_text())) for a,b in args.pair],
                      treatment_fields=('environment', 'amd_helper', 'amd_device',
                                        'amd_vram_mib', 'amd_decode_only', *args.treatment_field))
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text)

if __name__ == '__main__':
    main()
