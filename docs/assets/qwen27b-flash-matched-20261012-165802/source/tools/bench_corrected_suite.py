"""Versioned, separately labeled benchmark corrections. Historical packs untouched."""
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bench_lib import load_pack
VERSION='contract-v1'
CORRECTIONS={
 'e6-index-rebuild':'State the positive chunk size requirement already enforced by the checker.',
 'e12-schema-migration':'State duplicate migration names are invalid, matching checker semantics.',
 'e18-ttl-cache':'State boolean delete return, which differs from the old fixture behavior.',
 'e24-fsm-parallel':'State action callback arguments and None-result fallback, matching checker semantics.',
 'e7-money-rounding':'Use Decimal multiplication as the prompt promises int_or_decimal; float support is not required.',
 'e9-parallel-dedup':'Prove bounded consumption by observing offered items before put_if_absent; old test checked only final consumption.',
 'e11-scheduler-priority':'Remove private _streak coupling; enforce fairness overriding priority through observable run order.',
 'e13-stream-window':'Reset measurement via fresh module loading instead of undeclared _peak; verify bounded live input objects in addition to self-reported peak.',
 'e14-parser-precedence':'Declare modulo, decimal literals, numeric token values and arithmetic-zero errors already required by the checker.',
 'e17-batch-chunking':'Define processed as successfully completed chunks, failed as failed chunks; keep historical numeric expectation.',
 'e23-config-layers':'Dotted DROP removes the nested key, as explicitly required by the prompt.',
}
E9_EXTRA=r'''
# Bounded consumption must be observable before the whole input is exhausted.
s7 = Store()
observed = {'pulled': 0, 'offered': 0}
original_put = s7.put_if_absent
def tracked_put(key, value):
    observed['offered'] += 1
    return original_put(key, value)
s7.put_if_absent = tracked_put
def bounded_source():
    for i in range(30):
        observed['pulled'] += 1
        assert observed['pulled'] - observed['offered'] <= 5, 'materialised input beyond one chunk'
        yield ('bounded-%d' % i, i)
assert s7.process(bounded_source(), chunk=5) == {'stored': 30, 'duplicates': 0}
'''
E11_EXTRA=r'''
# Fairness overrides even unequal priorities; no private counter name is required.
rf = Runner(max_per_tenant=2)
rf.submit('a', lambda: 'a1', priority=100)
rf.submit('a', lambda: 'a2', priority=90)
rf.submit('a', lambda: 'a3', priority=80)
rf.submit('b', lambda: 'b1', priority=-100)
assert rf.run() == ['a1', 'a2', 'b1', 'a3'], 'fairness must override priority'
'''
E13_EXTRA=r'''
# Real retention check: reporting a peak does not prove bounded memory.
import gc
import weakref
live_values = weakref.WeakSet()
class TrackedValue:
    def __init__(self, number):
        self.number = number
        live_values.add(self)
def tracked_source():
    for i in range(300):
        yield (None, TrackedValue(i))
g = iter(Windowed(tracked_source(), 7, lambda values: len(values)))
n_windows = 0
for result in g:
    assert result == (None, 7)
    n_windows += 1
    gc.collect()
    assert len(live_values) <= 8, 'retained earlier windows or eagerly loaded source'
assert n_windows == 300 // 7
'''
def load_corrected_pack(name='deepswe2'):
    p=copy.deepcopy(load_pack(name))
    if name!='deepswe2':return p
    p['correction_version']=VERSION
    for t in p['tasks']:
        tid=t['id'];check=t['check']
        if tid=='e6-index-rebuild':
            t['prompt']=t['prompt'].replace('1. `build(pairs, chunk=64)`', 'The chunk size must be positive; zero or a negative size raises `ValueError`.\n1. `build(pairs, chunk=64)`')
        elif tid=='e12-schema-migration':
            t['prompt']=t['prompt'].replace('A missing dep or a dependency cycle raises', 'Duplicate migration names, a missing dep or a dependency cycle raise')
        elif tid=='e18-ttl-cache':
            t['prompt']=t['prompt'].replace('5. `delete(key)` removes it;', '5. `delete(key)` removes it and returns True if it existed, otherwise False;')
        elif tid=='e24-fsm-parallel':
            t['prompt']=t['prompt'].replace('4. `action` runs AFTER state is updated and its return value is returned by `go`.', '4. `action` runs AFTER state is updated, called as `action(new_state)` with no context keywords. A non-None action result is returned by `go`; if the action returns None, `go` returns the new state.')
        if tid=='e7-money-rounding':
            check=check.replace("assert (a * 1.5).cents == 1500", "assert (a * Decimal('1.5')).cents == 1500")
        elif tid=='e9-parallel-dedup':check+='\n'+E9_EXTRA
        elif tid=='e11-scheduler-priority':
            check=check.replace('assert r._streak <= 2','')+'\n'+E11_EXTRA
        elif tid=='e13-stream-window':
            # A class high-water mark covers its whole lifetime. Tests needing
            # independent maxima load a fresh public class, not a private field.
            check=check.replace('Windowed._peak = 0', "import importlib\nWindowed = importlib.reload(importlib.import_module(Windowed.__module__)).Windowed")
            check+='\n'+E13_EXTRA
        elif tid=='e14-parser-precedence':
            t['prompt']=t['prompt'].replace('`* / //`', '`* / // %`')
            t['prompt']=t['prompt'].replace('4. Integer operands and `/` produce exact float division; `//` floors.', '4. Integer and decimal literals (for example 4.5) are supported. `/` produces float division; `//` floors; `%` computes the remainder. Division, floor division or modulo by zero raises `ExprError`.')
            t['prompt']=t['prompt'].replace('6. `tokenize(text)` returns the token list and is also exported.', '6. `tokenize(text)` returns a list containing numeric values for integer/decimal tokens and strings for operators and parentheses; for example `tokenize("2 ** 3") == [2, "**", 3]`. It is also exported and rejects empty input or bad tokens with `ExprError`.')
        elif tid=='e17-batch-chunking':
            t['prompt']=t['prompt'].replace('4. `run_batches` reports totals via', '4. `processed` counts successfully completed chunks; `failed` counts failed chunks. `run_batches` reports totals via')
        elif tid=='e23-config-layers':
            old="assert d3['n'] == {'x': 1, 'y': 2}, 'a dotted key whose parent exists keeps the value unless explicitly targeted'"
            assert old in check
            check=check.replace(old,"assert d3['n'] == {'y': 2}, 'dotted DROP must remove the nested key'")
        t['check']=check
    return p

def hashes():
    original=load_pack('deepswe2');corrected=load_corrected_pack()
    return {o['id']:dict(original_prompt=hashlib.sha256(o['prompt'].encode()).hexdigest(),corrected_prompt=hashlib.sha256(c['prompt'].encode()).hexdigest(),original_check=hashlib.sha256(o['check'].encode()).hexdigest(),corrected_check=hashlib.sha256(c['check'].encode()).hexdigest(),reason=CORRECTIONS.get(o['id'])) for o,c in zip(original['tasks'],corrected['tasks'])}
