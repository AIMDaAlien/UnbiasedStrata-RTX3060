#!/usr/bin/env python3
"""Positive/negative/contract-mutant selftests for separate corrected suite."""
import ast,copy,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from bench_lib import extract_files,grade_assert,block
from bench_corrected_suite import load_corrected_pack,hashes
from strata_corrected import corrected_grade
spec=importlib.util.spec_from_file_location('references',ROOT/'selftest-deepswe2.py');refs=importlib.util.module_from_spec(spec);spec.loader.exec_module(refs)

def corrected_reference(tid):
    ref=copy.deepcopy(refs.REF[tid])
    if tid=='e23-config-layers':
        path='cfgx/merge.py';old="""        for path, val in dotted.items():
            if val is not DROP:
                _dotted_set(out, path, val)""";new="""        for path, val in dotted.items():
            if val is DROP:
                _dotted_del(out, path)
            else:
                _dotted_set(out, path, val)""";assert old in ref[path];ref[path]=ref[path].replace(old,new)
    if tid=='e11-scheduler-priority':
        ref={k:v.replace('_streak','_consecutive_jobs') for k,v in ref.items()}
    if tid=='e13-stream-window':
        ref={k:v.replace('_peak','_high_water') for k,v in ref.items()}
    return ref

def main():
    results=[];failed=[]
    for t in load_corrected_pack()['tasks']:
        tid=t['id'];ref=corrected_reference(tid)
        neg=refs.run_check(t['kit'],{},t['check'],timeout=t.get('timeout',300))
        pos=refs.run_check(t['kit'],ref,t['check'],timeout=t.get('timeout',300))
        text='\n'.join('```file '+path+'\n'+content.rstrip()+'\n```' for path,content in ref.items())
        rt=refs.run_check(t['kit'],extract_files(text),t['check'],timeout=t.get('timeout',300))
        ok=neg[0] is False and pos[0] is True and rt[0] is True
        results.append(dict(task=tid,broken_fixture=neg,correct_reference=pos,file_roundtrip=rt,passed=ok))
        if not ok:failed.append(tid)
        print(tid,'PASS' if ok else 'FAIL',neg,pos,flush=True)
    mutant_results=[]
    for tid,old,new,label in [
        ('e9-parallel-dedup','it = iter(items)','it = iter(list(items))','eagerly materialised input'),
        ('e13-stream-window','for item in self.source:', '_retained = []\n        for item in self.source:', 'retained all earlier values'),
    ]:
        t=next(t for t in load_corrected_pack()['tasks'] if t['id']==tid)
        mutant=corrected_reference(tid)
        key=next(k for k,v in mutant.items() if old in v)
        mutant[key]=mutant[key].replace(old,new)
        if tid=='e13-stream-window':mutant[key]=mutant[key].replace('k, v = item','k, v = item\n            _retained.append(v)')
        result=refs.run_check(t['kit'],mutant,t['check'],timeout=t.get('timeout',300))
        mutant_results.append(dict(task=tid,mutation=label,grade=result,rejected=result[0] is False))
        if result[0] is not False:failed.append(tid+' mutant')
    # Every original code wrapper must execute: positives + empty program rejection.
    code_refs=json.loads((ROOT/'tools/corrected_code_refs.json').read_text())
    # Authored reference for historical word-count contract. Its semantic mismatch
    # with transformation steps is documented separately; this checks wiring.
    code_refs['t3-word-ladder-len']=dict(tag='authored legacy-check reference',answer='''```python
from collections import deque
def steps(begin, end, wordlist):
    words=set(wordlist)
    if end not in words:return -1
    q=deque([(begin,1)])
    seen={begin}
    while q:
        word,d=q.popleft()
        if word==end:return d
        for nxt in words:
            if nxt not in seen and len(nxt)==len(word) and sum(a!=b for a,b in zip(word,nxt))==1:
                seen.add(nxt);q.append((nxt,d+1))
    return -1
```''')
    code_results=[]
    for t in load_corrected_pack('code')['tasks']:
        pos=corrected_grade(code_refs[t['id']]['answer'],t)
        neg=corrected_grade('```python\npass\n```',t)
        names={node.slice.value for node in ast.walk(ast.parse(t['tests'])) if isinstance(node,ast.Subscript) and isinstance(node.value,ast.Name) and node.value.id=='ns' and isinstance(node.slice,ast.Constant) and isinstance(node.slice.value,str)}
        wrong_code='class Wrong:\n    def __init__(self,*args,**kwargs):pass\n    def __getattr__(self,name):return lambda *args,**kwargs:None\n'
        wrong_code+='\n'.join(name+' = Wrong' for name in sorted(names))
        wrong=corrected_grade('```python\n'+wrong_code+'\n```',t)
        ok=pos[0]==pos[1] and neg[0]<neg[1] and wrong[0]<wrong[1]
        code_results.append(dict(task=t['id'],positive=pos,empty_program=neg,wrong_implementation=wrong,passed=ok))
        if not ok:failed.append('code/'+t['id'])
    # Active function invocation distinguishes correct mutable-default fix from bug.
    t=load_corrected_pack('code')['tasks'][0]
    bad='```python\ndef collect(x, items=[]):\n    items.append(x)\n    return items\n```'
    bad_grade=corrected_grade(bad,t)
    assert bad_grade[0]<bad_grade[1],bad_grade
    out=ROOT/'results/strata-20261012-corrected-suite-selftests.json'
    out.write_text(json.dumps(dict(deepswe2=results,contract_mutants=mutant_results,code=code_results,failed=failed,hashes=hashes()),indent=2)+'\n')
    print('SUMMARY',len(results),'DeepSWE2;',len(code_results),'code; failures',failed,flush=True)
    return bool(failed)
if __name__=='__main__':raise SystemExit(main())
