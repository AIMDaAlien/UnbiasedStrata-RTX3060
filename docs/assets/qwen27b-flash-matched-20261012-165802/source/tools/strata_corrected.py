#!/usr/bin/env python3
"""Offline corrected code grading. Historical runner/packs remain unchanged."""
import argparse
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bench_lib import load_pack,block,grade_assert
from strata_summary import final_content

def corrected_grade(answer,task):
    tests=task['tests']
    if re.search(r'^def run\(ns\):',tests,re.M):tests+='\nrun(globals())\n'
    return grade_assert(block(answer,'python') or block(answer),tests)

def selftest():
    t=load_pack('code')['tasks'][0]
    gold="def collect(x, items=None):\n    if items is None: items=[]\n    items.append(x)\n    return items\n"
    bad="def collect(x, items=[]):\n    items.append(x)\n    return items\n"
    for code,passed in [(gold,True),(bad,False),('pass',False)]:
        ok,total,detail=corrected_grade('```python\n'+code+'```',t)
        assert (ok==total)==passed,(ok,total,detail)
    print('corrected grader selftest: valid implementation passes, mutable-default bug and empty implementation fail')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--tag',required=True);args=ap.parse_args();selftest()
    doc=json.loads((ROOT/'results'/f'{args.tag}.json').read_text())
    all_answers=[json.loads(x) for x in (ROOT/'results'/f'{args.tag}.answers.jsonl').read_text().splitlines()]
    targets={}
    for tid,d in doc['targets'].items():
        rows=[]
        for r in d['rows']:
            if r['domain']!='code':continue
            candidates=[a['answer'] for a in all_answers if a['id']==r['id']]
            if not candidates: raise RuntimeError('missing full answer '+r['id'])
            # One-target code campaigns; repeated task records use latest saved answer.
            answer=candidates[-1];task=next(t for t in load_pack(r['pack'])['tasks'] if t['id']==r['task'])
            ok,total,detail=corrected_grade(answer,task)
            rows.append(dict(id=r['id'],pack=r['pack'],tier=r['tier'],legacy_status=r['status'],legacy_ok=r['ok'],finish_reason=r.get('finish_reason'),final_content=final_content(r),ok=ok,total=total,status='pass' if ok==total else 'part' if ok else 'fail',detail=detail))
        targets[tid]=dict(rows=rows,n=len(rows),passes=sum(r['status']=='pass' for r in rows),completed_passes=sum(r['status']=='pass' and r.get('finish_reason') not in ('length',None) for r in rows),truncated_passes=sum(r['status']=='pass' and r.get('finish_reason')=='length' for r in rows),verified_final_output_passes=sum(r['status']=='pass' and r.get('finish_reason') not in ('length',None) and r['final_content'] is True for r in rows),final_content_unknown=sum(r['final_content'] is None for r in rows),reasoning_only_rows=sum(r['final_content'] is False for r in rows),checks=sum(r['ok'] for r in rows),checks_total=sum(r['total'] for r in rows),legacy_false_passes=[r['id'] for r in rows if r['legacy_status']=='pass' and r['status']!='pass'])
        print(args.tag,tid,targets[tid]['passes'],'/',len(rows),targets[tid]['legacy_false_passes'])
    out=ROOT/'results'/f'{args.tag}.corrected-code.json';out.write_text(json.dumps(dict(tag=args.tag,correction='invoke run(globals()) after defining code task test wrapper',targets=targets),indent=2)+'\n');print(out)
if __name__=='__main__':main()
