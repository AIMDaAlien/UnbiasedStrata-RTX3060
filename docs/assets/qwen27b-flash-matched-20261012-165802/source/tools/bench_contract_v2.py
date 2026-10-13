"""Proposed original-suite repairs, separate from frozen DeepSWE2 contract-v1."""
import copy,hashlib,json,re,sys
from decimal import Decimal,InvalidOperation
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from bench_corrected_suite import load_corrected_pack,E9_EXTRA,E13_EXTRA
from strata_research_audit import facts
VERSION='contract-v2'
CORRECTIONS={
 'code/t2-lru':'Declare missing-key sentinel -1 required by existing checker.',
 'code/t4-lru-ttl':'Declare expired/missing sentinel -1 required by existing checker.',
 'code/t2-retry':'Return the last exception object as the existing prompt explicitly requires; do not require raising.',
 'code/t3-word-ladder-len':'Count transformation edges rather than path words, as prompt says.',
 'research/r2-legacy-owner':'Compute gold from actual legacy service described in supplied corpus.',
 'research/r4-team-rollup':'Accept structured alternative tied winners instead of literal platform|edge.',
 'research/r4-port-hunt':'Accept every section whose retry ceiling reaches the tied maximum.',
 'deepswe2/e9-parallel-dedup':'Observe bounded retention through weakly tracked duplicate values, without assuming method dispatch or mutable instances.',
 'deepswe2/e13-stream-window':'Declare key callback input and summarise output pairs; isolate peak measurements in fresh processes importing only the public package.',
 'deepswe2/e12-schema-migration':'Explicitly undo this-call successful records on failure and return undone migration names from rollback_last.',
 'deepswe2/e20-iter-drain':'Specify that aggregated close-error text includes captured exception messages; preserve existing closure and cause checks.',
 'deepswe2/e21-index-invalidation':'Accept an actual name set or sorted unique sequence, avoiding an undocumented concrete Python-container requirement.',
 'deepswe2/e22-multiprocess-shard':'Specify that shard elements are string IDs, also passed as infer text, and output names use those exact IDs.',
 'deepswe2/e10-csv-dialect':'Declare that Reader.read returns a Reader instance with rows() and fieldnames; original helper return type was unspecified.',
 'deepswe2/e4-session-store-split':'Drop an undocumented public backend-attribute requirement; retain every observable delegation/TTL/default behavior check.',
 'terminal/t3-symlink-repair':'Accept either alias representative for each repaired target; make rule explicit.',
}
RETRY_TESTS='''
def run(ns):
    f = ns['retry']
    calls = {'n': 0}
    def flaky():
        calls['n'] += 1
        if calls['n'] < 3:
            raise ValueError('no')
        return 'ok'
    assert f(flaky, 5) == 'ok' and calls['n'] == 3
    last = KeyError('x')
    failed_calls = []
    def fails():
        failed_calls.append(1)
        raise last
    assert f(fails, 2) is last, 'return the last exception object'
    assert len(failed_calls) == 2
'''

E9_PUBLIC_EXTRA = r'''
# Observe public memory behavior without assuming virtual method dispatch,
# instance mutability, hash hooks, or internal locking/data structures.
import gc
import weakref
live_inputs = weakref.WeakSet()
class InputValue:
    __slots__ = ('number', '__weakref__')
    def __init__(self, number):
        self.number = number
        live_inputs.add(self)
chunk_size = 5
s7 = Store()
def bounded_source():
    for i in range(40):
        value = InputValue(i)
        gc.collect()
        # A previous batch may overlap construction of the next batch, and
        # the accepted first value remains stored. Allow that benign overlap.
        assert len(live_inputs) <= 2 * chunk_size + 3, 'materialised/retained the whole input'
        yield ('one-key', value)
assert s7.process(bounded_source(), chunk=chunk_size) == {'stored': 1, 'duplicates': 39}
assert s7.get('one-key').number == 0
'''
E13_FRESH_PROBES = r'''
# Each high-water measurement gets fresh state without naming private fields
# or assuming the class implementation module exports the public alias.
import subprocess
import sys
probe = """
import sys
from swin import Windowed
from swin.agg import total
case = int(sys.argv[1])
if case == 1:
    size = 5
    source = ((None, i) for i in range(10000))
    key = None
    expected = 10000 // size
elif case == 2:
    size = 4
    source = (('k%d' % (i % 7), i) for i in range(700))
    key = lambda pair: pair[0]
    expected = 700 // size
else:
    size = 3
    source = ((None, i) for i in range(20000))
    key = None
    expected = 20000 // size
assert sum(1 for _ in Windowed(source, size, total, key=key)) == expected
assert Windowed.peak_memory() == size, Windowed.peak_memory()
"""
for case in (1, 2, 3):
    proc = subprocess.run([sys.executable, '-c', probe, str(case)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, (case, proc.stderr)
'''

def load_contract_v2_pack(name):
    p=copy.deepcopy(load_corrected_pack(name));p['correction_version']=VERSION
    if name=='deepswe2':
        for t in p['tasks']:
            if t['id']=='e4-session-store-split':
                old='assert isinstance(s4.backend, MemoryStore)';assert old in t['check']
                t['check']=t['check'].replace(old,'')
            elif t['id']=='e9-parallel-dedup':
                assert E9_EXTRA in t['check']
                t['check']=t['check'].replace(E9_EXTRA,E9_PUBLIC_EXTRA)
            elif t['id']=='e12-schema-migration':
                old="6. If a migration's `up` raises, everything applied during THIS call is rolled back by calling each applied migration's `down` in REVERSE order, the failing migration is NOT recorded, and the original exception propagates."
                assert old in t['prompt']
                t['prompt']=t['prompt'].replace(old,old+' Remove the records for migrations successfully applied during this call when rolling them back; retain all records that existed before this call.')
                old='7. `rollback_last(conn, migrations, db)` undoes the most recent recorded migration and removes its record.'
                assert old in t['prompt']
                t['prompt']=t['prompt'].replace(old,old+' Return the undone migration name, or None when there is no recorded migration.')
            elif t['id']=='e13-stream-window':
                old='4. If `key` is None the whole stream is one key `None`.'
                assert old in t['prompt']
                t['prompt']=t['prompt'].replace(old,old+' Otherwise call `key(original_pair)` with the original `(key, value)` pair, not only its value.')
                old='6. `summarise(source, size, fn, key=None)` is a convenience that returns a list of all results.'
                assert old in t['prompt']
                t['prompt']=t['prompt'].replace(old,'6. `summarise(source, size, fn, key=None)` returns `list(Windowed(source, size, fn, key))`, preserving every emitted `(key, result)` pair.')
                start=t['check'].index('# MEMORY BOUND:')
                end=t['check'].index("print('ok')",start)
                t['check']=t['check'][:start]+E13_FRESH_PROBES+'\n'+t['check'][end:]
            elif t['id']=='e20-iter-drain':
                old='5. `close_all(sources)` closes every source, collecting exceptions, and raises a `DrainError` describing the failures at the end (all sources get closed even if some raise).'
                assert old in t['prompt']
                t['prompt']=t['prompt'].replace(old,old+' The text of that `DrainError` must include the captured close-exception messages.')
            elif t['id']=='e21-index-invalidation':
                old='5. `Graph.missing()` returns the sorted set of required names that no module provides.'
                assert old in t['prompt']
                t['prompt']=t['prompt'].replace(old,'5. `Graph.missing()` returns required names that no module provides, either as a set or as a sorted unique sequence.')
                helper="""
from collections.abc import Set as NameSet
def assert_missing_names(graph, expected):
    actual = graph.missing()
    assert not isinstance(actual, (str, bytes)), 'missing names must be a collection'
    names = list(actual)
    assert len(names) == len(set(names)), 'missing names must be unique'
    assert set(names) == expected, names
    if not isinstance(actual, NameSet):
        assert names == sorted(names), 'a sequence of missing names must be sorted'
"""
                t['check']=helper+'\n'+t['check'].replace("assert g3.missing() == {'Z'}, g3.missing()","assert_missing_names(g3, {'Z'})").replace('assert g3.missing() == set()','assert_missing_names(g3, set())')
            elif t['id']=='e22-multiprocess-shard':
                old='1. `Worker(model, shards, out_dir, checkpoint_every=10)`;'
                assert old in t['prompt']
                t['prompt']=t['prompt'].replace(old,'The `shards` argument is a sequence of string shard IDs. Each element is both the exact output shard ID and the text passed to `model.infer`; do not substitute its enumeration index.\n'+old)
            elif t['id']=='e10-csv-dialect':
                clause='4. `Reader.read(path_or_text)` is a classmethod-ish helper: if the argument is an existing path it opens that file, otherwise it treats the string as the CSV text itself.'
                assert clause in t['prompt']
                t['prompt']=t['prompt'].replace(clause,clause+' It returns a `Reader` instance, supporting both `.rows()` and `.fieldnames`.')
    elif name=='triage':
        tasks=[]
        for original in p['tasks']:
            source,tid=original['id'].split(':',1)
            fixed=next(t for t in load_contract_v2_pack(source)['tasks'] if t['id']==tid)
            fixed=copy.deepcopy(fixed);fixed['id']=original['id'];fixed['domain']=original['domain'];tasks.append(fixed)
        p['tasks']=tasks
    elif name=='code':
        for t in p['tasks']:
            if t['id']=='t2-lru':
                t['prompt']+='\n`get(key)` returns -1 for a missing key.'
            elif t['id']=='t4-lru-ttl':
                t['prompt']+='\n`get(key)` returns -1 for a missing or expired key.'
            elif t['id']=='t2-retry':
                t['tests']=RETRY_TESTS
                t['prompt']+='\nWhen all attempts fail, RETURN the final exception object; do not raise it.'
            elif t['id']=='t3-word-ladder-len':
                old="assert f('hit','cog',['hot','dot','dog','lot','log','cog']) == 5"
                assert old in t['tests'];t['tests']=t['tests'].replace(old,old[:-1]+'4')
                t['tests']+="    assert f('a', 'b', ['b']) == 1\n"
                t['prompt']+='\nCount single-letter transformations (edges), not the number of words in the path.'
    elif name=='research':
        expected,_=facts()
        for t in p['tasks']:
            t['required']=expected[t['id']]
            t['grading_contract']=VERSION
            if t['id']=='r4-team-rollup':
                t['prompt']+='\nIf teams tie for the highest count, naming either tied team with that count is accepted.'
            elif t['id']=='r4-port-hunt':
                t['prompt']+='\nIf multiple services tie for the highest ceiling, cite any section documenting a tied service.'
    elif name=='terminal':
        for t in p['tasks']:
            if t['id']=='t3-symlink-repair':
                old="assert fixed == ['a', 'b'], fixed";assert old in t['check']
                t['check']=t['check'].replace(old,"assert fixed in (['a', 'b'], ['b', 'ok']), fixed")
                t['prompt']+='\nIf multiple dangling links refer to the same missing target, creating that target repairs them all. List exactly one representative link per newly created target; any representative is accepted, and the report must be sorted.'
    return p

def grade_research_contract_v2(text,required,banned=()):
    total=len(required);text=text or ''
    lower=text.lower()
    for b in banned:
        if b.lower() in lower:return 0,total,'banned:'+b[:40]
    match=re.fullmatch(r'\s*([^\n]+?)\s*@\s*§([1-9]\d*)\s*',text)
    if not match:return 0,total,'answer-format'
    values=match[1].lower();section='§'+match[2]
    # Consume a whole numeric-looking token before validating thousands groups;
    # never match the 7 inside -7, 17.7, 7.1, or malformed grouped values.
    number_like = r'(?<![\w.+-])[+-]?(?:\d+(?:,\d+)*(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?(?![\w.])'
    valid_number = r'[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?'
    numbers=set()
    for token in re.findall(number_like,values):
        if not re.fullmatch(valid_number,token):continue
        try:numbers.add(Decimal(token.replace(',','')))
        except InvalidOperation:pass
    def present(marker):
        marker=str(marker).lower()
        if marker.startswith('§'):return marker==section
        if marker.isdigit():return Decimal(marker) in numbers
        return re.search(r'(?<!\w)'+re.escape(marker)+r'(?!\w)',values) is not None
    hits=sum(any(present(v) for v in choice) if isinstance(choice,(list,tuple)) else present(choice) for choice in required)
    return hits,total,'ok' if hits==total else f'{hits}/{total}'

def fingerprint(name):
    p=load_contract_v2_pack(name)
    return {t['id']:{k:hashlib.sha256(json.dumps(t.get(k),sort_keys=True).encode()).hexdigest() for k in ['prompt','tests','check','required']} for t in p['tasks']}
