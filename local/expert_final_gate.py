#!/usr/bin/python3
"""Fresh final response gate, then authorized screening/acceptance only if qualified."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,indent=2)+'\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output.resolve();base=out/'final-profiles/baseline.json';frozen=json.loads((out/'final-build-manifest.json').read_text());binary=ROOT/'build-expert-lab/unbiased-strata'
 assert sha(binary)==frozen['executable_sha256']['unbiased-strata']
 for stage in ['parity/mode5','sanitizer/mode5-memcheck','sanitizer/mode5-racecheck','sanitizer/mode5-synccheck','micro/mode5-independent']:
  p=out/stage;assert json.loads((p/'state.json').read_text())['status']=='passed';assert all(json.loads((p/'integrity.json').read_text())['checks'].values())
 def run(stage,mode,path):
  assert sha(binary)==frozen['executable_sha256']['unbiased-strata']
  with (out/(path.replace('/','-')+'.log')).open('w') as log:
   subprocess.run([sys.executable,str(ROOT/'local/expert_campaign.py'),'--output',str(out/path),'--baseline-profile',str(base),'--stage',stage,'--variant',str(mode)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
  assert sha(binary)==frozen['executable_sha256']['unbiased-strata']
 results={}
 for name,mode in [('control',0),('candidate',5)]:
  path='profile/final-'+name;run('profile',mode,path);record=json.loads((out/path/'run/results.json').read_text());assert record['status']=='passed';assert record['launch']['binary_sha256']==frozen['executable_sha256']['unbiased-strata'];results[name]=record
  # Verify actual compiled dispatch, including control in every unmeasured row class.
  entries={(x['format'],x['phase'],x['row_class']):x['mode'] for x in json.loads((out/'winning-dispatch.json').read_text())['dispatch_table']}
  observed=set()
  for line in (out/path/'run/engine.log').read_text().splitlines():
   if not line.startswith('native_expert_profile '):continue
   q=json.loads(line.split(' ',1)[1]);assert q['requested_variant']==mode
   phase=1 if q['phase']=='gate_up_epilogue' else 2;n=q['total_routed_rows'];e=q['total_experts'];cl=0 if n<=56*e else 1 if n<=112*e else 2;expected=0 if mode==0 else entries[(q['format'],phase,cl)];assert q['variant']==expected;observed.add((q['format'],phase,cl,q['variant']))
  save(out/path/'dispatch-observed.json',{'cells':[list(x) for x in sorted(observed)],'verified':True})
 r0={r['target_tokens']:r for r in results['control']['runs']};r5={r['target_tokens']:r for r in results['candidate']['runs']};ratios={str(n):r5[n]['wall_seconds']/r0[n]['wall_seconds'] for n in [128000,180000]};passed=all(r<=.95 for r in ratios.values())
 report={'status':'passed' if passed else 'rejected','profiled_total_response_ratios':ratios,'minimum_required_improvement_percent':5,'both_lengths_required':True,'same_binary_sha256':frozen['executable_sha256']['unbiased-strata'],'all_fresh_quality_checks_passed':True,'profiling_excluded_from_acceptance_statistics':True,'earlier_disconnected_runs_used_only_for_selection':True,'production_changed':False,'next_action':'one uninstrumented screening pair' if passed else 'stop this bounded kernel campaign; no screening or acceptance warranted'}
 save(out/'profile-gate.json',report)
 if not passed:return
 run('screen',5,'screening');screen=json.loads((out/'screening/report.json').read_text())
 if not screen['screen_passed']:
  save(out/'campaign-decision.json',dict(status='rejected_screening',screening=screen,production_changed=False));return
 run('accept',5,'acceptance');accept=json.loads((out/'acceptance/report.json').read_text());save(out/'campaign-decision.json',dict(status='accepted' if accept['accepted'] else 'rejected_acceptance',acceptance=accept,production_changed=False))
if __name__=='__main__':main()
