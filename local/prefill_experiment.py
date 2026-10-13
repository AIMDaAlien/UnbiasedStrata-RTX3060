#!/usr/bin/python3
"""Measured single-GPU tuning; isolated profiles and unchanged canonical fixtures."""
import argparse, fcntl, hashlib, json, math, time
from pathlib import Path
from launch import CONFIG, ROOT, command, optimization_environment
from long_context import run, CHECKPOINTS
from paired_report import evaluate

FIXTURES = ROOT / 'local/benchmarks/long-20261010-v4/fixtures'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--stage', choices=('screen', 'tune', 'verify', 'paired', 'amd'), default='screen')
    ap.add_argument('--candidate', type=Path)
    ap.add_argument('--baseline-profile', type=Path, help='explicit baseline; preserves its fusion setting')
    ap.add_argument('--complete-pairs', action='store_true',
                    help='run all five acceptance pairs without the first-pair feasibility stop')
    a = ap.parse_args()
    a.output = a.output.resolve()
    a.output.mkdir(parents=True, exist_ok=True)
    lock = open(ROOT / 'local/long-context.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    base = json.loads((a.baseline_profile or CONFIG).read_text())
    base.update(context=196608, port=18081)
    base.pop('amd_helper', None)
    # Materialize inherited controls into the profile so resume and pairing
    # cannot treat ambient experiment variables as invisible defaults.
    base['environment'] = dict(base.get('environment', {}), **optimization_environment(base))
    if a.baseline_profile is None:
        base['environment']['STRATA_PF_FUSED'] = '0'
    import subprocess
    cap = float(subprocess.check_output(['nvidia-smi','--id=0','--query-gpu=power.limit',
                '--format=csv,noheader,nounits'],text=True).strip())
    if cap != 100: raise RuntimeError('benchmark requires the existing 100 W GPU limit')
    def measured(profile, path, lengths=(80000,), workloads=('fresh',)):
        path = a.output / path
        if (path/'results.json').exists():
            old = json.loads((path/'results.json').read_text())
            if old['profile'] != profile: raise RuntimeError('resume profile mismatch')
            launch=old.get('launch') or json.loads((path/'launch.json').read_text())
            current_hash=hashlib.sha256(Path(command(profile)[0]).read_bytes()).hexdigest()
            if launch['binary_sha256'] != current_hash:
                raise RuntimeError('resume binary differs; use a new output directory')
            if launch['environment'] != optimization_environment(profile):
                raise RuntimeError('resume optimization environment differs')
            if old['status'] == 'passed': return old
            raise RuntimeError('failed result already exists; use new output path')
        return run(profile, lengths, workloads, path, FIXTURES)
    if a.stage == 'screen':
        candidates = [
            ('baseline', {}),
            ('fused-auto', {'STRATA_PF_FUSED':'1'}),
            ('fused-tile64', {'STRATA_PF_FUSED':'1','STRATA_PF_FUSED_TILE':'64'}),
            ('fused-tile128', {'STRATA_PF_FUSED':'1','STRATA_PF_FUSED_TILE':'128'}),
        ]
        records = []
        for name, changes in candidates:
            profile = dict(base, environment=dict(base['environment'], STRATA_PREFILL_TIMING='1', **changes))
            r = measured(profile, 'screen/'+name)
            records.append({'name':name, 'status':r['status'], 'profile':profile,
                            'wall_seconds':r['runs'][0]['wall_seconds'] if r['status']=='passed' else None})
            (a.output/'screen.json').write_text(json.dumps(records,indent=2)+'\n')
        passed = [r for r in records if r['status']=='passed']
        baseline=records[0]
        if baseline['status']!='passed': raise RuntimeError('baseline quality gate failed')
        winner=baseline
        for trial in passed[1:]:
            # Screen noise is not evidence for forcing an otherwise automatic knob.
            if trial['wall_seconds'] < winner['wall_seconds'] * .98:
                winner=trial
        winner['profile']['environment'].pop('STRATA_PREFILL_TIMING',None)
        (a.output/'candidate.json').write_text(json.dumps(winner['profile'],indent=2)+'\n')
    else:
        candidate = json.loads((a.candidate or a.output/'candidate.json').read_text())
        if a.baseline_profile is not None:
            candidate['environment']['STRATA_PREFILL_TIMING'] = None
        else:
            candidate['environment'].pop('STRATA_PREFILL_TIMING',None)
        if a.stage == 'tune':
            records=[]
            def screen(name, profile):
                profile=dict(profile,environment=dict(profile['environment'], STRATA_PREFILL_TIMING='1'))
                r=measured(profile,'tune/'+name)
                info=dict(name=name,status=r['status'],profile=profile,
                          wall_seconds=r['runs'][0]['wall_seconds'] if r['status']=='passed' else None)
                records.append(info)
                (a.output/'tune.json').write_text(json.dumps(records,indent=2)+'\n')
                return info
            current=screen('current',candidate)
            for ceiling in (16384,32768):
                profile=dict(candidate,environment=dict(candidate['environment'],STRATA_PREFILL_AUTO_MAX=str(ceiling)))
                trial=screen('chunk'+str(ceiling),profile)
                if trial['status']=='passed' and trial['wall_seconds']<current['wall_seconds']*.98:
                    current=trial
            chosen=current['profile']
            for ring in (128,256,512):
                profile=dict(chosen,environment=dict(chosen['environment'],STRATA_PREFILL_RING=str(ring)))
                trial=screen('ring'+str(ring),profile)
                if trial['status']=='passed' and trial['wall_seconds']<current['wall_seconds']*.98:
                    current=trial
            current['profile']['environment'].pop('STRATA_PREFILL_TIMING',None)
            (a.output/'candidate.json').write_text(json.dumps(current['profile'],indent=2)+'\n')
        elif a.stage == 'amd':
            amd=dict(candidate,amd_helper=str(ROOT/'local/amd-worker.sh'),
                     amd_device='GPU-8140af32fe338274',amd_vram_mib=12288,amd_decode_only=True)
            records={name:measured(profile,'amd/'+name,CHECKPOINTS,('fresh','growing'))
                     for name,profile in [('baseline',candidate),('decode-only',amd)]}
            if all(r['status']=='passed' for r in records.values()):
                report=evaluate([(records['baseline'],records['decode-only'])])
            else:
                report={'status':'AMD feasibility/quality failure; excluded from speed results'}
            report['profiles']={k:r['profile'] for k,r in records.items()}
            (a.output/'amd-decision.json').write_text(json.dumps(report,indent=2)+'\n')
        elif a.stage == 'verify':
            for name, profile in [('baseline',base),('candidate',candidate)]:
                measured(profile,'verify/'+name,CHECKPOINTS,('fresh','growing'))
        else:
            pairs=[]
            for repetition in range(5):
                records={}
                for name, profile in ([('baseline',base),('candidate',candidate)] if repetition%2==0
                                      else [('candidate',candidate),('baseline',base)]):
                    records[name]=measured(profile,f'paired/{repetition}/{name}',CHECKPOINTS,('fresh','growing'))
                    if records[name]['status']!='passed': raise RuntimeError('paired quality failure')
                pairs.append((records['baseline'],records['candidate']))
                report=evaluate(pairs)
                report['candidate_baseline_geomean_ratio']=report.pop('amd_on_off_geomean_ratio')
                report['eligible_3060']=len(pairs)==5 and report['paired_95_ci_ratio'][1]<1 and max(report['bucket_ratios'].values())<=1.05
                report['candidate']=candidate
                (a.output/'decision.json').write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps(report),flush=True)
                if not a.complete_pairs and repetition == 0 and (report['candidate_baseline_geomean_ratio'] >= 1
                        or max(report['bucket_ratios'].values()) > 1.05):
                    report['feasibility_stop'] = (
                        'first pair showed no aggregate speedup or a bucket regression above 5%')
                    (a.output/'decision.json').write_text(json.dumps(report,indent=2)+'\n')
                    print(json.dumps(report),flush=True)
                    break
if __name__=='__main__': main()
