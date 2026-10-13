#!/usr/bin/env python3
"""Positive/negative coverage for proposed original-suite contract-v2 repairs."""
import ast,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from bench_lib import block,grade_assert,grade_cmd,extract_files
from bench_contract_v2 import load_contract_v2_pack,grade_research_contract_v2,fingerprint

RETRY='''def retry(fn, times):
    last = None
    for _ in range(times):
        try: return fn()
        except Exception as error: last = error
    return last
'''
LADDER='''from collections import deque
def steps(begin,end,wordlist):
    if begin==end:return 0
    words=set(wordlist)
    if end not in words:return -1
    q=deque([(begin,0)]);seen={begin}
    while q:
        word,d=q.popleft()
        if word==end:return d
        for nxt in words:
            if nxt not in seen and len(nxt)==len(word) and sum(a!=b for a,b in zip(word,nxt))==1:
                seen.add(nxt);q.append((nxt,d+1))
    return -1
'''

def main():
    refs=json.loads((ROOT/'tools/corrected_code_refs.json').read_text());records=[]
    for t in load_contract_v2_pack('code')['tasks']:
        if t['id'] not in ['t2-lru','t4-lru-ttl','t2-retry','t3-word-ladder-len']:continue
        code=RETRY if t['id']=='t2-retry' else LADDER if t['id']=='t3-word-ladder-len' else block(refs[t['id']]['answer'],'python')
        good=grade_assert(code,t['tests']);empty=grade_assert('pass',t['tests'])
        if t['id']=='t2-retry':wrong=RETRY.replace('return last','raise last')
        elif t['id']=='t3-word-ladder-len':wrong=LADDER.replace('if word==end:return d','if word==end:return d+1')
        else:
            # This is a real API-value mutant: replace the validated get method
            # at the end of the module without disturbing put/expiry state.
            cname='LRU' if t['id']=='t2-lru' else 'TLRU'
            wrong=code+f'\n_original_get={cname}.get\ndef wrong_get(self,key):\n    value=_original_get(self,key)\n    return None if value==-1 else value\n{cname}.get=wrong_get\n'
        bad=grade_assert(wrong,t['tests']);assert good[0]==good[1] and empty[0]<empty[1] and bad[0]<bad[1],(t['id'],good,empty,bad)
        records.append(dict(task='code/'+t['id'],positive=good,empty=empty,wrong_semantics=bad))
    for t in load_contract_v2_pack('research')['tasks']:
        req=t['required'];sections=[str(c) for item in req for c in (item if isinstance(item,list) else [item]) if str(c).startswith('§')]
        section=sections[0] if sections else '§1'
        values=[str(item[0] if isinstance(item,list) else item) for item in req if not (isinstance(item,str) and item.startswith('§')) and not (isinstance(item,list) and item[0].startswith('§'))]
        good=grade_research_contract_v2(', '.join(values)+' @ '+section,req)
        empty=grade_research_contract_v2('',req);wrong=grade_research_contract_v2('zzzz @ §999',req)
        assert good[0]==good[1] and empty[0]<empty[1] and wrong[0]<wrong[1],(t['id'],good,empty,wrong)
        if t['id']=='r4-port-hunt':
            for s in sections:assert grade_research_contract_v2('53 @ '+s,req)[0]==len(req)
        if t['id']=='r4-team-rollup':
            for team in req[0]:assert grade_research_contract_v2(team+', 7 @ §1',req)[0]==len(req)
        records.append(dict(task='research/'+t['id'],positive=good,empty=empty,wrong=wrong))
    assert grade_research_contract_v2('platform, 17 @ §1',[['platform','edge'],'7'])[0]==1
    for wrong_number in ['-7','7.1','17.7','7,42','a-7','7.1.0','7e2']:
        assert grade_research_contract_v2('platform, '+wrong_number+' @ §1',[['platform','edge'],'7'])[0]==1,wrong_number
    assert grade_research_contract_v2('platform, 7.0 @ §1',[['platform','edge'],'7'])[0]==2
    assert grade_research_contract_v2('7,424 @ §1',['7424'])[0]==1
    assert grade_research_contract_v2('-7,424 @ §1',['7424'])[0]==0
    assert grade_research_contract_v2('wrong @ §7',['7','§7'])[0]==1
    assert grade_research_contract_v2('wrong @ §15',['15','§15'])[0]==1
    assert grade_research_contract_v2('metadata @ §30',['data','§3'])[0]==0
    t=next(t for t in load_contract_v2_pack('terminal')['tasks'] if t['id']=='t3-symlink-repair')
    outcomes=[]
    for report,valid in [('a\nb\n',True),('b\nok\n',True),('b\n',False),('a\nb\nok\n',False)]:
        code="printf '\\n' > links/data/x.txt\nprintf '\\n' > links/data/y.txt\ncat > fixed.txt <<'REPORT'\n"+report+'REPORT\n'
        answer='```bash\n'+code+'```';grade=grade_cmd(answer,'bash',t['kit'],t['check']);assert (grade[0]==grade[1])==valid,(report,grade);outcomes.append(dict(report=report,valid=valid,grade=grade))
    records.append(dict(task='terminal/t3-symlink-repair',cases=outcomes))
    # Public behavior must accept any private storage field name and reject
    # silently ignoring an explicitly provided backend.
    from selftest_corrected_suite import corrected_reference,refs as deepswe_refs
    t=next(t for t in load_contract_v2_pack('deepswe2')['tasks'] if t['id']=='e4-session-store-split')
    reference=corrected_reference(t['id'])
    private_reference={k:v.replace('self.backend','self._storage') for k,v in reference.items()}
    positive=deepswe_refs.run_check(t['kit'],private_reference,t['check'])
    broken=deepswe_refs.run_check(t['kit'],{},t['check'])
    bad_reference=copy.deepcopy(private_reference)
    old='backend if backend is not None else MemoryStore('
    assert old in bad_reference['sess/store.py']
    bad_reference['sess/store.py']=bad_reference['sess/store.py'].replace(old,'MemoryStore(')
    bad=deepswe_refs.run_check(t['kit'],bad_reference,t['check'])
    assert positive[0] is True and broken[0] is False and bad[0] is False,(positive,broken,bad)
    records.append(dict(task='deepswe2/e4-session-store-split',private_field_reference=positive,broken_fixture=broken,ignores_supplied_backend=bad))
    csv_task=next(t for t in load_contract_v2_pack('deepswe2')['tasks'] if t['id']=='e10-csv-dialect')
    csv_reference=corrected_reference(csv_task['id'])
    csv_good=deepswe_refs.run_check(csv_task['kit'],csv_reference,csv_task['check'])
    csv_broken=deepswe_refs.run_check(csv_task['kit'],{},csv_task['check'])
    csv_bad=copy.deepcopy(csv_reference)
    csv_bad['imp/csvimport.py']=csv_bad['imp/csvimport.py'].replace('return cls(f.read())','return cls(f.read()).rows()').replace('return cls(path_or_text)','return cls(path_or_text).rows()')
    csv_wrong=deepswe_refs.run_check(csv_task['kit'],csv_bad,csv_task['check'])
    assert csv_good[0] is True and csv_broken[0] is False and csv_wrong[0] is False,(csv_good,csv_broken,csv_wrong)
    records.append(dict(task='deepswe2/e10-csv-dialect',reader_factory=csv_good,broken_fixture=csv_broken,row_generator_factory=csv_wrong))
    deep_full=[]
    for task in load_contract_v2_pack('deepswe2')['tasks']:
        reference=corrected_reference(task['id'])
        negative=deepswe_refs.run_check(task['kit'],{},task['check'])
        positive=deepswe_refs.run_check(task['kit'],reference,task['check'])
        text='\n'.join('```file '+path+'\n'+content.rstrip()+'\n```' for path,content in reference.items())
        roundtrip=deepswe_refs.run_check(task['kit'],extract_files(text),task['check'])
        assert negative[0] is False and positive[0] is True and roundtrip[0] is True,(task['id'],negative,positive,roundtrip)
        deep_full.append(dict(task=task['id'],broken=negative,reference=positive,roundtrip=roundtrip))
        print('DEEP',task['id'],'PASS',flush=True)
    structural=[]
    dedup_task=next(t for t in load_contract_v2_pack('deepswe2')['tasks'] if t['id']=='e9-parallel-dedup')
    dedup=corrected_reference(dedup_task['id']);key='pdedup/store.py'
    attrs=sorted({n.attr for n in ast.walk(ast.parse(dedup[key])) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='self' and isinstance(n.ctx,ast.Store)})
    slotted=copy.deepcopy(dedup);slotted[key]=slotted[key].replace('class Store:','class Store:\n    __slots__ = '+repr(tuple(attrs)),1)
    slotted_grade=deepswe_refs.run_check(dedup_task['kit'],slotted,dedup_task['check'])
    qualified=copy.deepcopy(slotted)
    qualified[key]=qualified[key].replace('self.put_if_absent(key, value)','Store.put_if_absent(self, key, value)')
    qualified_grade=deepswe_refs.run_check(dedup_task['kit'],qualified,dedup_task['check'])
    assert qualified_grade[0] is True,qualified_grade
    eager=copy.deepcopy(dedup);assert 'it = iter(items)' in eager[key];eager[key]=eager[key].replace('it = iter(items)','it = iter(list(items))')
    eager_grade=deepswe_refs.run_check(dedup_task['kit'],eager,dedup_task['check'])
    assert slotted_grade[0] is True and eager_grade[0] is False,(slotted_grade,eager_grade)
    structural.append(dict(task=dedup_task['id'],slotted_positive=slotted_grade,qualified_dispatch_positive=qualified_grade,eager_negative=eager_grade))
    window_task=next(t for t in load_contract_v2_pack('deepswe2')['tasks'] if t['id']=='e13-stream-window')
    window=corrected_reference(window_task['id'])
    alias={'swin/_impl.py':window['swin/window.py'].replace('Windowed','RollingEngine'),'swin/window.py':'from ._impl import RollingEngine as Windowed, summarise\n'}
    alias_grade=deepswe_refs.run_check(window_task['kit'],alias,window_task['check'])
    retained=copy.deepcopy(window);retained['swin/window.py']=retained['swin/window.py'].replace('for item in self.source:','_retained = []\n        for item in self.source:').replace('k, v = item','k, v = item\n            _retained.append(v)')
    retained_grade=deepswe_refs.run_check(window_task['kit'],retained,window_task['check'])
    assert alias_grade[0] is True and retained_grade[0] is False,(alias_grade,retained_grade)
    structural.append(dict(task=window_task['id'],public_alias_positive=alias_grade,retaining_negative=retained_grade))
    migration_task=next(t for t in load_contract_v2_pack('deepswe2')['tasks'] if t['id']=='e12-schema-migration')
    stale=corrected_reference(migration_task['id']);assert 'db.applied_migrations.remove(name)' in stale['mig/runner.py'];stale['mig/runner.py']=stale['mig/runner.py'].replace('db.applied_migrations.remove(name)','pass',1)
    stale_grade=deepswe_refs.run_check(migration_task['kit'],stale,migration_task['check']);assert stale_grade[0] is False,stale_grade
    structural.append(dict(task=migration_task['id'],stale_bookkeeping_negative=stale_grade))
    code_full=[]
    for task in load_contract_v2_pack('code')['tasks']:
        code=RETRY if task['id']=='t2-retry' else LADDER if task['id']=='t3-word-ladder-len' else block(refs[task['id']]['answer'],'python')
        positive=grade_assert(code,task['tests']);empty=grade_assert('pass',task['tests'])
        assert positive[0]==positive[1] and empty[0]<empty[1],(task['id'],positive,empty)
        code_full.append(dict(task=task['id'],reference=positive,empty=empty))
    triage=load_contract_v2_pack('triage')
    for t in triage['tasks']:
        if t['id']=='code:t4-lru-ttl':assert 'missing or expired key' in t['prompt']
        if t['id']=='research:r2-legacy-owner':assert t['required']==['75','security','§10']
    out=ROOT/'results/strata-20261012-contract-v2-selftests.json';out.write_text(json.dumps(dict(records=records,deep_full=deep_full,structural_mutants=structural,code_full=code_full,triage_propagation=True,hashes={p:fingerprint(p) for p in ['code','research','terminal','triage','deepswe2']}),indent=2)+'\n');print('PASS',len(records),'repair cases; full24 DeepSWE2 and40 code pass; structural mutants rejected; triage/marker cases pass')
if __name__=='__main__':main()
