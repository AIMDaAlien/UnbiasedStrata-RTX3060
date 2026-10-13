#!/usr/bin/python3
"""Run fixed code-task checks with restricted syntax, builtins and process limits."""
import ast
import json
import resource
import sys

request = json.load(sys.stdin)
code = request['code']
if len(code) > 16000:
    raise SystemExit(1)
tree = ast.parse(code)
allowed_methods = {'append', 'extend', 'get', 'setdefault', 'pop', 'add', 'copy', 'sort', 'items', 'values', 'keys'}
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.ClassDef,
                         ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom)):
        raise SystemExit(1)
    if isinstance(node, ast.Attribute) and node.attr not in allowed_methods:
        raise SystemExit(1)
    if isinstance(node, ast.Name) and node.id.startswith('_'):
        raise SystemExit(1)
    if isinstance(node, (ast.FunctionDef, ast.arg)) and (node.name if isinstance(node, ast.FunctionDef) else node.arg).startswith('_'):
        raise SystemExit(1)
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
safe = {k: getattr(__builtins__, k) for k in ('len', 'range', 'enumerate', 'sorted', 'list', 'dict',
        'tuple', 'set', 'min', 'max', 'sum', 'zip', 'int', 'bool', 'abs', 'ValueError')}
scope = {'__builtins__': safe}
exec(compile(tree, '<local-benchmark-answer>', 'exec'), scope)
name = request['task']
function = scope[name]
if name == 'merge_ranges':
    cases = [([], []), ([[1,5],[2,6],[8,10]], [[1,6],[8,10]]),
             ([[4,6],[1,2],[2,4]], [[1,6]]), ([[1,3],[1,3]], [[1,3]])]
    for values, expected in cases:
        original = [v[:] for v in values]
        assert json.loads(json.dumps(function(values))) == expected and values == original
elif name == 'ordered_results':
    events = [{'seq':2,'status':'done','value':'b'}, {'seq':1,'status':'cancelled'},
              {'seq':0,'status':'done','value':'old'}, {'seq':0,'status':'done','value':'a'}]
    assert function(events) == ['a','b']
    assert function([]) == []
    assert function([{'seq':0,'status':'done','value':'x'},{'seq':0,'status':'cancelled'}]) == []
elif name == 'batch_records':
    records = [['a',2],['b',1],['c',2],['d',4],['e',1]]
    assert function(records,3,5) == [records[:3],records[3:]]
    assert function(records,1,5) == [[r] for r in records]
    assert function([],3,5) == []
    for records in ([['x',6]], [['x',-1]]):
        try:
            function(records,3,5)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid size was accepted')
else:
    raise SystemExit(1)
print('passed')
