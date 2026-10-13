#!/usr/bin/python3
"""Aggregate paired microbenchmarks; select only >=5% gains, ties within 1% prefer simpler modes."""
import argparse,json,math,statistics
from collections import defaultdict
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--input',type=Path,action='append',required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
groups=defaultdict(list);resources={};combined=defaultdict(list);inputs=[];fallbacks=[]
for path in a.input:
 state=json.loads((path/'state.json').read_text())
 if state['status']!='passed':raise ValueError('incomplete benchmark excluded')
 profile=json.loads((path/'profile.json').read_text());variant=int(profile['environment']['STRATA_PF_NATIVE_VARIANT']);base=profile['environment'].get('STRATA_PF_NATIVE_BASE');prefetchbase=profile['environment'].get('STRATA_PF_NATIVE_PREFETCH_BASE');records=[json.loads(s) for s in (path/'raw.jsonl').read_text().splitlines() if s.startswith('{')];samples=defaultdict(dict)
 for r in records:
  if r['kind']=='resource':resources[(path.name,r['layer'],r['class'],r['phase'])]=r
  if r['kind']=='timing':samples[(r['layer'],r['class'],r['phase'],r['pair'])][r['variant']]=r['ms']
 for (layer,cl,phase,pair),ms in samples.items():
  if set(ms)!={0,variant}:raise ValueError('missing alternating timing pair')
  ratio=ms[variant]/ms[0]
  if phase==0:combined[variant].append(ratio);continue
  info=resources[(path.name,layer,cl,phase)]
  if info['variant']==0:
   fallbacks.append(dict(path=str(path),layer=layer,row_class=cl,phase=phase,format=info['format'],requested_mode=variant));continue
  if info['variant']!=variant and not (variant==5 and info.get('requested_variant')==5):raise ValueError('unexpected effective variant')
  key=(info['format'],phase,cl,variant,str(base),str(prefetchbase));groups[key].append(ratio)
 inputs.append({'path':str(path),'variant':variant,'base':base,'prefetch_base':prefetchbase,'standalone_sha256':json.loads((path/'stage-manifest.json').read_text()).get('standalone_sha256')})
if not combined:raise ValueError('benchmark missing timing samples')
ratios=[dict(format=k[0],phase=k[1],row_class=k[2],mode=k[3],base=None if k[4]=='None' else int(k[4]),prefetch_base=None if k[5]=='None' else int(k[5]),paired_geomean_ratio=math.exp(statistics.mean(map(math.log,rs))),pairs=len(rs)) for k,rs in groups.items()];bykey=defaultdict(list)
for row in ratios:bykey[(row['format'],row['phase'],row['row_class'])].append(row)
table=[]
for fmt,phase in [(t,1) for t in [16,17,18,21,22]]+[(t,2) for t in [20,42]]:
 for cl in range(3):
  candidates=[r for r in bykey[(fmt,phase,cl)] if r['paired_geomean_ratio']<=.95]
  winner={'format':fmt,'phase':phase,'row_class':cl,'mode':0,'base':None,'prefetch_base':None,'reason':'no measured >=5% improvement'}
  if candidates:
   best=min(r['paired_geomean_ratio'] for r in candidates);winner=min([r for r in candidates if r['paired_geomean_ratio']<=best*1.01],key=lambda r:r['mode']).copy();winner['reason']='fastest qualifying mode; ties within 1% prefer simpler mode'
  table.append(winner)
report={'inputs':inputs,'unavailable_specialization_fallbacks':fallbacks,'ratios':ratios,'combined_ratio_by_mode':{v:math.exp(statistics.mean(map(math.log,rs))) for v,rs in combined.items()},'dispatch_table':table,'microbenchmark_only':True,'unobserved_classes_keep_control':True}
a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'combined_ratio_by_mode':report['combined_ratio_by_mode'],'candidate_entries':sum(r['mode']!=0 for r in table)},indent=2))
