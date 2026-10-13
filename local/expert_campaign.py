#!/usr/bin/python3
"""Isolated expert campaign stages; never changes or starts production."""
import argparse,copy,datetime,fcntl,hashlib,json,os,signal,subprocess,threading,time
import long_context
from pathlib import Path
from launch import ROOT,CONFIG,optimization_environment
from long_context import run,CHECKPOINTS
from paired_report import evaluate
FIXTURES=ROOT/'local/benchmarks/long-20261010-v4/fixtures'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  while b:=f.read(8*1024**2):h.update(b)
 return h.hexdigest()
def save(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,indent=2)+'\n');tmp.replace(p)
def gpu(allowed=()):
 cap=float(subprocess.check_output(['nvidia-smi','--id=0','--query-gpu=power.limit','--format=csv,noheader,nounits'],text=True).strip())
 if cap!=100:raise RuntimeError('100 W frozen limit changed')
 ps=subprocess.check_output(['nvidia-smi','--id=0','--query-compute-apps=pid,process_name','--format=csv,noheader'],text=True)
 for line in ps.splitlines():
  pid=int(line.split(',')[0]);cg=Path(f'/proc/{pid}/cgroup')
  if pid in allowed:continue
  if cg.exists() and any(x in cg.read_text() for x in (f'unbiasedstrata-long-{os.getpid()}-',f'strata-expert-{os.getpid()}-')):
   group=Path('/sys/fs/cgroup')/cg.read_text().strip().split('::',1)[1].lstrip('/')
   if (group/'memory.swap.current').exists() and int((group/'memory.swap.current').read_text())!=0:raise RuntimeError('workload swap detected')
   continue
  raise RuntimeError('unexpected GPU owner: '+line)
 if subprocess.run(['systemctl','--user','is-active','--quiet','unbiasedstrata.service']).returncode==0:raise RuntimeError('production started')
original_completion=long_context.completion
def verified_completion(*args,**kwargs):
 gpu()
 return original_completion(*args,**kwargs)
long_context.completion=verified_completion
def moment():
 return {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'monotonic_ns':time.monotonic_ns(),'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
class Guard:
 def __init__(self,allowed=()):self.allowed=allowed;self.stop=threading.Event();self.error=None
 def __enter__(self):
  def watch():
   while not self.stop.wait(2):
    try:gpu(self.allowed)
    except Exception as e:self.error=str(e);os.kill(os.getpid(),signal.SIGINT);return
  self.worker=threading.Thread(target=watch,daemon=True);self.worker.start();return self
 def __exit__(self,*args):self.stop.set();self.worker.join(timeout=5)
def measured(p,path,lengths=CHECKPOINTS,workloads=('fresh','growing')):
 if path.exists():raise RuntimeError('fresh evidence directory required: '+str(path))
 gpu()
 with Guard() as guard:r=run(p,lengths,workloads,path,FIXTURES)
 if guard.error:raise RuntimeError(guard.error)
 if r['status']!='passed':raise RuntimeError('quality failed: '+str(path))
 return r
def profiling(r,path):
 rows=[]
 for line in (path/'engine.log').read_text().splitlines():
  if line.startswith('native_expert_profile '):rows.append(json.loads(line.split(' ',1)[1]))
 if not rows:raise RuntimeError('native phase diagnostics absent')
 sums={}
 for q in rows:
  k=str(q['format'])+'/'+q['phase'];sums[k]=sums.get(k,0)+q['elapsed_ms']
 return {'status':r['status'],'requests':[{'tokens':q['target_tokens'],'total_response_seconds':q['wall_seconds'],'timings':q['timings'],'checks':q['checks'],'prefill_diagnostics':q['prefill_diagnostics']} for q in r['runs']],'supplemental_phase_totals_ms':sums,'records':len(rows)}
def routes(path,dest):
 counts=[0]*512;seen=set();routes={0:[],1:[],2:[]}
 for line in (path/'engine.log').read_text().splitlines():
  if not line.startswith('native_expert_profile '):continue
  q=json.loads(line.split(' ',1)[1])
  if q['phase']!='gate_up_epilogue':continue
  start=q['batch_start'];counts[start:start+q['batch_experts']]=q['expert_rows'];seen.update(range(start,start+q['batch_experts']))
  if len(seen)==512:
   avg=sum(counts)/512;cl=0 if avg<=56 else 1 if avg<=112 else 2;routes[cl].append(counts[:]);counts=[0]*512;seen=set()
 chosen={cl:sorted(rs,key=sum)[len(rs)//2] for cl,rs in routes.items() if rs}
 dest.write_text(''.join(str(cl)+' '+' '.join(map(str,c))+'\n' for cl,c in chosen.items()))
 save(dest.with_suffix('.json'),{'observed_counts_by_class':{cl:len(rs) for cl,rs in routes.items()},'selected_counts':chosen})
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);ap.add_argument('--baseline-profile',required=True,type=Path);ap.add_argument('--stage',required=True,choices=['profile','parity','compact','bench','sanitizer','screen','accept']);ap.add_argument('--variant',type=int,default=0);ap.add_argument('--sanitizer-tool',choices=['memcheck','racecheck','synccheck'],default='memcheck');ap.add_argument('--base',type=int);ap.add_argument('--prefetch-base',type=int);a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 lock=open(ROOT/'local/long-context.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 p=json.loads(a.baseline_profile.read_text());p['environment']['STRATA_PF_NATIVE_VARIANT']=str(a.variant)
 if a.base is not None:p['environment']['STRATA_PF_NATIVE_BASE']=str(a.base)
 if a.prefetch_base is not None:p['environment']['STRATA_PF_NATIVE_PREFETCH_BASE']=str(a.prefetch_base)
 if a.stage=='profile':p=copy.deepcopy(p);p['environment'].update(STRATA_PREFILL_TIMING='1',STRATA_PF_NATIVE_PROFILE='1')
 gpu();started=moment()
 source_files=[ROOT/x for x in ['src/prefill/moe_fused_iq.cu','src/kernels/native_expert_lab.cpp','include/strata/prefill/moe_fused_iq_lab.hpp','include/strata/prefill/moe_fused_iq_dispatch.hpp','local/expert_campaign.py','local/long_context.py','local/launch.py']]
 identity=json.loads((a.baseline_profile.parent/'manifest.json').read_text())['model_pack_identity']
 model_stats={f:{'size':Path(f).stat().st_size,'mtime_ns':Path(f).stat().st_mtime_ns,'inode':Path(f).stat().st_ino} for f in identity}
 manifest={'started':started,'binary_sha256':sha(p['binary']),'standalone_sha256':sha(Path(p['binary']).parent/'native_expert_lab'),'source_sha256':{str(x):sha(x) for x in source_files},'model_file_stats':model_stats,'memory_max_bytes':56*1024**3,'memory_swap_max_bytes':0,'environment':optimization_environment(p),'fixture_sha256':{x.name:sha(x) for x in FIXTURES.glob('*.json')},'production_profile_sha256':sha(CONFIG),'baseline_profile_sha256':sha(a.baseline_profile)}
 save(out/'profile.json',p);save(out/'stage-manifest.json',manifest)
 state={'status':'running','stage':a.stage,'variant':a.variant,'production_changed':False};save(out/'state.json',state)
 try:
  if a.stage in ('parity','compact','bench','sanitizer'):
   cmd=[str(Path(p['binary']).parent/'native_expert_lab'),p['pack'],p['model'],'compact' if a.stage=='sanitizer' else a.stage,str(a.variant)]
   if a.stage=='sanitizer' and a.sanitizer_tool!='memcheck':cmd.append('narrow')
   if a.stage=='sanitizer':cmd=['/opt/cuda/bin/compute-sanitizer','--tool',a.sanitizer_tool,'--error-exitcode','99',*cmd]
   if a.stage=='bench':cmd.append(str((a.baseline_profile.parent/'observed-routing.txt').resolve()))
   with (out/'raw.jsonl').open('w') as log:
    env={k:v for k,v in os.environ.items() if not k.startswith('STRATA_')};env.update(optimization_environment(p));unit=f'strata-expert-{os.getpid()}-{time.time_ns()}';cmd=['systemd-run','--user','--pipe','--wait','--collect','--quiet',f'--unit={unit}','--property=MemoryMax=56G','--property=MemorySwapMax=0','--property=TimeoutStopSec=30','--property=KillMode=control-group','/usr/bin/env',*[f'{k}={v}' for k,v in optimization_environment(p).items()],*cmd];child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env)
    try:
     with Guard((child.pid,)) as guard:code=child.wait()
    finally:
     if child.poll() is None:subprocess.run(['systemctl','--user','stop',unit]);child.wait(timeout=35)
    if guard.error:raise RuntimeError(guard.error)
   if code:raise RuntimeError('standalone failed, exit '+str(code))
   if a.stage=='bench':
    data=[json.loads(s) for s in (out/'raw.jsonl').read_text().splitlines() if s.startswith('{')]
    if not any(r['kind']=='timing' for r in data) or not any(r['kind']=='resource' for r in data):raise RuntimeError('benchmark produced no timing/resource samples')
  elif a.stage=='profile':
   r=measured(p,out/'run',(128000,180000),('fresh',));save(out/'summary.json',profiling(r,out/'run'))
   if a.variant==0:routes(out/'run',a.baseline_profile.parent/'observed-routing.txt')
  else:
   control=json.loads(a.baseline_profile.read_text());pairs=[]
   for i in range(1 if a.stage=='screen' else 5):
    pair={};order=('control','candidate') if i%2==0 else ('candidate','control')
    for name in order:pair[name]=measured(control if name=='control' else p,out/str(i)/name)
    pairs.append((pair['control'],pair['candidate']));report=evaluate(pairs,treatment_fields=('environment',));ratio=report.pop('amd_on_off_geomean_ratio');report.pop('eligible_to_enable');ci=report['paired_95_ci_ratio'];report.update(total_response_ratio=ratio,screen_passed=ratio<=.95 and max(report['bucket_ratios'].values())<=1.05,accepted=len(pairs)==5 and ratio<=.95 and ci[1]<1 and max(report['bucket_ratios'].values())<=1.05,production_changed=False);save(out/'report.json',report)
   if a.stage=='accept' and not report['accepted']:raise RuntimeError('acceptance thresholds not met')
  ended=moment()
  integrity={'same_boot':ended['boot_id']==started['boot_id'],'engine_binary_unchanged':sha(p['binary'])==manifest['binary_sha256'],'standalone_binary_unchanged':sha(Path(p['binary']).parent/'native_expert_lab')==manifest['standalone_sha256'],'source_unchanged':all(sha(x)==h for x,h in manifest['source_sha256'].items()),'fixtures_unchanged':all(sha(FIXTURES/name)==h for name,h in manifest['fixture_sha256'].items()),'production_config_unchanged':sha(CONFIG)==manifest['production_profile_sha256'],'baseline_profile_unchanged':sha(a.baseline_profile)==manifest['baseline_profile_sha256'],'model_files_unchanged':all({'size':Path(f).stat().st_size,'mtime_ns':Path(f).stat().st_mtime_ns,'inode':Path(f).stat().st_ino}==x for f,x in model_stats.items())}
  save(out/'integrity.json',dict(checks=integrity,started=started,ended=ended))
  if not all(integrity.values()):raise RuntimeError('stage integrity changed; exclude measurements')
  state.update(status='passed',started=started,ended=ended)
 except BaseException as e:state.update(status='failed_or_incomplete',error=str(e));raise
 finally:save(out/'state.json',state)
if __name__=='__main__':main()
