#!/usr/bin/env python3
"""Validate research gold against current corpus and grade provable alternatives offline."""
import argparse,collections,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from bench_lib import load_pack

def facts():
 p=load_pack('research');s=p['_corpus_text'];services=[]
 for m in re.finditer(r'## §(\d+) — ([^\n]+)\n(.*?)(?=\n## §|\Z)',s,re.S):
  sec,name,body=m.groups();owner=re.search(r'publishes on port (\d+) and is owned by the (\w+) team',body);f=re.search(r'outbound retry ceiling is (\d+) attempts.*?audit trail is kept for (\d+) days',body)
  if owner and f:services.append(dict(section=int(sec),name=name,port=int(owner[1]),team=owner[2].lower(),retry=int(f[1]),retention=int(f[2]),legacy='only service still' in body))
 table={region:list(map(int,re.findall(r'\d+',numbers))) for region,numbers in re.findall(r'^\| (Northland|Southreach|Eastgate|Westvane) \| (.*?) \|$',s,re.M)}
 expected={};audit=[]
 for t in p['tasks']:
  tid=t['id']; gold=list(t['required']); grounded=None
  if tid.startswith('r1-'):
   svc=next(x for x in services if x['name'] in t['prompt']);key='retry' if 'retry' in tid else 'retention' if 'retention' in tid else 'team';grounded=[str(svc[key]),f"§{svc['section']}"]
  elif tid=='r2-legacy-owner':
   svc=next(x for x in services if x['legacy']);grounded=[str(svc['retention']),svc['team'],f"§{svc['section']}"]
  elif tid=='r2-port-to-team':
   svc=next(x for x in services if str(x['port']) in t['prompt']);grounded=[svc['team'],str(svc['retry']),f"§{svc['section']}"]
  elif tid=='r3-table-q3sum':grounded=[str(sum(table[r][2] for r in table if r in t['prompt'])),'§9']
  elif tid=='r3-table-total':grounded=[str(sum(map(sum,table.values()))),'§9']
  elif tid=='r3-table-argmax':
   name=max(table,key=lambda r:table[r][3]);grounded=[name.lower(),str(table[name][3]),'§9']
  elif tid=='r4-contradiction':
   svc=next(x for x in services if x['name'] in t['prompt']);overview=int(re.search(re.escape(svc['name'])+r' keeps its audit trail for (\d+) days',s)[1]);assert svc['retention']<overview;grounded=[str(svc['retention']),f"§{svc['section']}"]
  elif tid=='r4-team-rollup':
   count=collections.Counter(x['team'] for x in services);n=max(count.values());grounded=[[k for k,v in count.items() if v==n],str(n)]
  elif tid=='r4-port-hunt':
   n=max(x['retry'] for x in services);grounded=[[f"§{x['section']}" for x in services if x['retry']==n],str(n)]
  assert grounded is not None
  expected[tid]=grounded;audit.append(dict(task=tid,stored_required=gold,document_grounded_required=grounded,valid=gold==grounded))
 return expected,dict(services=services,table=table,tasks=audit)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--tag');args=ap.parse_args();expected,audit=facts();(ROOT/'results/strata-20261011-research-grader-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
 print('expectation differences',[t['task'] for t in audit['tasks'] if not t['valid']])
 if not args.tag:return
 d=json.loads((ROOT/'results'/f'{args.tag}.json').read_text());answers={a['id']:a['answer'] for a in map(json.loads,(ROOT/'results'/f'{args.tag}.answers.jsonl').read_text().splitlines())};targets={}
 for tid,data in d['targets'].items():
  rows=[]
  for r in data['rows']:
   if r['domain']!='research':continue
   task=r['task'].split(':')[-1];answer=answers[r['id']].lower();req=expected[task];ok=sum(any(v.lower() in answer for v in x) if isinstance(x,list) else x.lower() in answer for x in req);total=len(req)
   rows.append(dict(id=r['id'],legacy_status=r['status'],legacy_ok=r['ok'],ok=ok,total=total,status='pass' if ok==total else 'part' if ok else 'fail',finish_reason=r.get('finish_reason'),document_grounded_required=req,answer=answers[r['id']]))
  targets[tid]=dict(rows=rows,n=len(rows),passes=sum(r['status']=='pass' for r in rows),checks=sum(r['ok'] for r in rows),checks_total=sum(r['total'] for r in rows))
 out=ROOT/'results'/f'{args.tag}.document-grounded-research.json';out.write_text(json.dumps(dict(tag=args.tag,scope='current generated corpus; historical source corpus identity unverified',targets=targets),indent=2)+'\n');print(out)
if __name__=='__main__':main()
