#!/usr/bin/python3
"""Resumeable local tuning, long-context verification, paired acceptance and rollout."""
import argparse
import fcntl
import itertools
import json
from pathlib import Path
import subprocess
import time

from launch import CONFIG, ROOT
from long_context import run, CHECKPOINTS
from paired_report import evaluate, buckets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='apply only fully verified settings')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock = open(ROOT / 'local/long-context.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'unbiasedstrata.service']).returncode == 0:
        parser.error('stop production inference before the experiment')
    base = json.loads(CONFIG.read_text())
    base.update(context=196608, port=18081)
    base.pop('amd_helper', None)
    amd = dict(base, amd_helper=str(ROOT / 'local/amd-worker.sh'),
               amd_device='GPU-8140af32fe338274', amd_vram_mib=12288)
    fixtures = output / 'fixtures'
    settings = [(t,s,k,w) for t,s in itertools.product((8,12,15,16),(2,4))
                for k,w in [('int8',0),('k8v4',0),('q4_0',0),('int8',32768),('int8',65536)]]
    def measured(profile, lengths, workloads, path):
        previous = path / 'results.json'
        if previous.exists():
            old = json.loads(previous.read_text())
            if old['profile'] != profile:
                raise RuntimeError('resume profile mismatch: '+str(path))
            if old['status'] != 'interrupted' and not (old['status']=='failed' and 'error' not in old):
                print('Reusing completed experiment:', path, old['status'], flush=True)
                return old
        print('Testing', profile, lengths, workloads, path, flush=True)
        return run(profile, lengths, workloads, path, fixtures)
    verified = {mode:{} for mode in ('off','on')}
    amd_seed = None
    for mode, config in [('off',base),('on',amd)]:
        screens = []
        if mode == 'on':
            off_results = json.loads((output/'off-screen.json').read_text())
            amd_seed = min(off_results, key=lambda r:r['runs'][0]['wall_seconds'])['profile']
        for t,s,k,w in settings:
            if mode == 'on' and (t,s,k,w) != (amd_seed['threads'], amd_seed['spec'],
                                                  amd_seed['kv'], amd_seed['kv_resident']):
                continue
            p = dict(config,threads=t,spec=s,kv=k,kv_resident=w)
            r = measured(p,(80000,),('fresh',),output/'screen'/mode/f't{t}-s{s}-{k}-w{w}')
            if r['status']=='passed': screens.append(r)
        (output/f'{mode}-screen.json').write_text(json.dumps(screens,indent=2)+'\n')
        # Keep the two fastest 80K candidates per KV precision; both streaming
        # windows compete with plain INT8. Verify the exact 180K input next.
        for kv in ('int8','k8v4','q4_0'):
            pool = [r for r in screens if r['profile']['kv']==kv]
            if kv == 'int8':
                # Preserve representation across plain and both RAM-backed windows.
                candidates = [min((r for r in pool if r['profile']['kv_resident']==window),
                                  key=lambda r:r['runs'][0]['wall_seconds'])
                              for window in (0,32768,65536)
                              if any(r['profile']['kv_resident']==window for r in pool)]
            else:
                candidates = sorted(pool, key=lambda r:r['runs'][0]['wall_seconds'])[:2]
            passing = []
            for i,r in enumerate(candidates):
                checked = measured(r['profile'],(180000,),('fresh',),output/'180k'/mode/kv/str(i))
                if checked['status']=='passed':
                    passing.append((r['runs'][0]['wall_seconds']*checked['runs'][0]['wall_seconds'],r['profile']))
            if passing:
                verified[mode][kv] = min(passing,key=lambda p:p[0])
    common = set(verified['off']) & set(verified['on'])
    report = {'verified_candidates':verified,'amd_enabled':False}
    if not verified['off']:
        report['status']='no passing long-context baseline; production unchanged'
        (output/'decision.json').write_text(json.dumps(report,indent=2)+'\n')
        raise SystemExit(1)
    # Compare both independently tuned modes at the same KV precision. Select
    # the precision with the fastest combined verified 80K/180K wall times.
    kv = min(common,key=lambda k:verified['off'][k][0]*verified['on'][k][0]) if common else min(
        verified['off'],key=lambda k:verified['off'][k][0])
    baseline_kv = min(verified['off'],key=lambda k:verified['off'][k][0])
    baseline_profile = verified['off'][baseline_kv][1]
    baseline = measured(baseline_profile,CHECKPOINTS,('fresh','growing'),output/'baseline')
    if baseline['status'] != 'passed':
        report['status']='fastest baseline failed full quality checks; production unchanged'
        (output/'decision.json').write_text(json.dumps(report,indent=2)+'\n')
        raise SystemExit(1)
    off_profile = verified['off'][kv][1]
    off = measured(off_profile,CHECKPOINTS,('fresh','growing'),output/'feasibility'/'off')
    if off['status']!='passed':
        report['status']='baseline failed full long-context quality checks; production unchanged'
        (output/'decision.json').write_text(json.dumps(report,indent=2)+'\n')
        raise SystemExit(1)
    winner = baseline_profile
    if common:
        on_profile=verified['on'][kv][1]
        on=measured(on_profile,CHECKPOINTS,('fresh','growing'),output/'feasibility'/'on')
        if on['status']=='passed':
            feasibility=evaluate([(off,on)])
            report['feasibility']=feasibility
            a,b=buckets(off),buckets(on)
            # Stop when every bucket is slower and transfer/wait dominates:
            # the helper's best screened configuration offers no useful overlap.
            slower=all(v>1 for v in feasibility['bucket_ratios'].values())
            if not slower:
                pairs=[]
                for repetition in range(5):
                    order=('off','on') if repetition%2==0 else ('on','off')
                    repetition_results={}
                    for mode in order:
                        repetition_results[mode]=measured(off_profile if mode=='off' else on_profile,
                            CHECKPOINTS,('fresh','growing'),output/'paired'/str(repetition)/mode)
                    if any(r['status']!='passed' for r in repetition_results.values()):
                        report['status']='paired repetition failed; AMD remains disabled'
                        break
                    pairs.append((repetition_results['off'],repetition_results['on']))
                if len(pairs)==5:
                    report['acceptance']=evaluate(pairs)
                    if report['acceptance']['eligible_to_enable']:
                        winner=on_profile
                        report['amd_enabled']=True
            else:
                report['status']='AMD slower in all six buckets after tuning; stopped before repetitions'
        else:
            report['status']='AMD failed feasibility quality or memory gate'
    else:
        report['status']='no passing AMD configuration at a matching KV precision'
    winner=dict(winner,port=json.loads(CONFIG.read_text())['port'])
    report['production_candidate']=winner
    if args.apply:
        stamp=time.strftime('%Y%m%d-%H%M%S')
        CONFIG.with_name('config.json.before-long-context-'+stamp).write_text(CONFIG.read_text())
        temp=CONFIG.with_suffix('.tmp'); temp.write_text(json.dumps(winner,indent=2)+'\n');temp.replace(CONFIG)
        client=Path.home()/'.config/opencode/opencode.json'
        if client.exists():
            document=json.loads(client.read_text())
            provider=document.get('provider',{}).get('local-strata',{})
            model=provider.get('models',{}).get('strata')
            if model is not None:
                client.with_name('opencode.json.before-long-context-'+stamp).write_text(client.read_text())
                model.setdefault('limit',{})['context']=196608
                temp=client.with_suffix('.tmp');temp.write_text(json.dumps(document,indent=2)+'\n');temp.replace(client)
        report['applied']=True
    (output/'decision.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':
    main()
