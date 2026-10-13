#!/usr/bin/env python3
"""Additional public-API probes, kept separate from frozen raw scores."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from bench_contract_v2 import load_contract_v2_pack
from bench_lib import extract_files
from selftest_corrected_suite import corrected_reference,refs
PROBES={
'e1':'''from wpool.queue import Queue,Closed
q=Queue(2);q.put('alpha');q.put('beta')
assert q.get()=='alpha' and q.get()=='beta' and q.unfinished==2
q.task_done();q.task_done();q.join(timeout=.1);q.close();assert q.get() is None
try:q.put('gamma');assert False
except Closed:pass
''',
'e2':'''from cachebox.lru import LRU
c=LRU(2);c.put('red',11);c.put('blue',22);assert c.get('red')==11
c.put('green',33);assert c.get('blue') is None and c.keys()==['green','red']
''',
'e3':'''from apiwrap.client import Client,Transient
calls=[]
def transport(*args):
 calls.append(args)
 if len(calls)<2:raise Transient('again')
 return (201,91)
c=Client(transport,backoff=0);assert c.call('POST','/x',idempotency_key='stable')==(201,91)
assert len(calls)==2 and all(x[3]['Idempotency-Key']=='stable' for x in calls)
''',
'e4':'''from sess import SessionStore,MemoryStore,UnknownSession
now=[100.0];b=MemoryStore(ttl=3,clock=lambda:now[0]);s=SessionStore(ttl=3,backend=b,clock=lambda:now[0]);s.set('x',{'v':8});assert b.get('x')=={'v':8}
now[0]=103.0
try:s.get('x');assert False
except UnknownSession:pass
''',
'e5':'''from vp import RequestQueue,BadType
q=RequestQueue({'id':{'type':int,'required':True}})
try:q.submit({'id':'bad'});assert False
except BadType:pass
assert q.pending()==0
q.submit({'id':7});assert q.drain()==[{'id':7}] and q.pending()==0
''',
'e6':'''from tindex import Index,build,merge
x=Index();x.rebuild([('a','red red'),('b','blue red')]);assert x.lookup('red')==['a','b']
x.rebuild([('z','green')]);assert x.lookup('red')==[] and x.lookup('green')==['z']
b={'x':{'a':[2,0]}};assert merge(b,[('x','a',[2,1])]) is b and b['x']['a']==[0,1,2]
''',
'e7':'''from ledger import Money
assert Money('1.005').cents==101 and Money('-1.005').cents==-101
parts=Money('.07').allocate([('a',1),('b',2)]);assert sum(x.cents for x in parts.values())==7
assert parts['b'].cents==5 and Money('-1.00').format()=='-$1.00'
''',
'e8':'''from evt.aggregate import Aggregate,InvalidEvent
x=Aggregate();x.apply({'name':'added','amount':9,'seq':71});before=(x.snapshot(),x.version,list(x.pending))
for event in [{'name':'added','amount':1,'seq':71},{'name':'unknown'}]:
 try:x.apply(event);assert False
 except InvalidEvent:pass
 assert (x.snapshot(),x.version,x.pending)==before
y=Aggregate().rehydrate([{'name':'added','amount':2},{'name':'added','amount':3}]);assert y.state=={'count':2,'total':5} and y.version==2
''',
'e9':'''from pdedup import Store
from concurrent.futures import ThreadPoolExecutor
s=Store()
with ThreadPoolExecutor(8) as pool:r=list(pool.map(lambda v:s.put_if_absent('same',v),range(40)))
assert sum(r)==1 and len(s)==1
assert s.process([('z',9),('z',10)],chunk=1)=={'stored':1,'duplicates':1}
''',
'e10':'''from imp import Reader
r=Reader(' a | b \\n"v|w"|"line1\\nline2"\\nonly\\n',dialect='pipe')
assert r.fieldnames==['a','b'] and list(r.rows())==[{'a':'v|w','b':'line1\\nline2'},{'a':'only','b':None}]
assert isinstance(Reader.read('x,y\\n3,4\\n'),Reader)
import tempfile,os
with tempfile.TemporaryDirectory() as d:
 path=os.path.join(d,'sample.csv')
 with open(path,'w') as f:f.write('x,y\\n3,4\\n')
 loaded=Reader.read(path);assert loaded.fieldnames==['x','y'] and list(loaded.rows())==[{'x':'3','y':'4'}]
''',
'e11':'''from sched import Runner
r=Runner(max_per_tenant=1)
for tenant,value,priority in [('a',1,9),('a',2,9),('b',3,0)]:r.submit(tenant,lambda v=value:v,priority=priority)
assert r.run()==[1,3,2] and r.pending()==0
''',
'e12':'''from mig import plan,migrate,applied
from types import SimpleNamespace
log=[];db=SimpleNamespace(applied_migrations=['old']);db.record=lambda n:db.applied_migrations.append(n)
def boom(c):raise RuntimeError('boom')
m=[{'name':'a','up':lambda c:log.append('up-a'),'down':lambda c:log.append('down-a'),'deps':[]},{'name':'b','up':boom,'down':lambda c:None,'deps':['a']}]
assert migrate(None,m,db,dry_run=True)==['a','b'] and log==[]
try:migrate(None,m,db);assert False
except RuntimeError as e:assert str(e)=='boom'
assert log==['up-a','down-a'] and applied(db)=={'old'}
''',
'e13':'''from swin import summarise
pairs=[('a',1),('b',10),('a',2),('b',20),('a',3)]
assert summarise(pairs,2,sum,key=lambda pair:pair[0])==[('a',3),('b',30)]
''',
'e14':'''from expr.parser import parse
assert parse('2 + 3 * 4')==14 and parse('2 ** 3 ** 2')==512 and parse('(2 + 3) * 4')==20
''',
'e15':'''from bpq import BoundedQueue,Closed
q=BoundedQueue(2);q.put(1);q.put(2);assert q.drop_oldest()==1;q.close()
assert q.get()==2 and q.get() is None
assert q.put(3) is False
''',
'e16':'''from ac import Trie
x=Trie();x.insert('Apple',2);x.insert('apricot',5);x.insert('app',5)
assert x.complete('AP')==['app','apricot','apple'] and x.longest_prefix_of('application')=='app'
x.remove('app');assert 'APP' not in x
''',
'e17':'''from batch import chunked,run_batches
pulled=[]
def source():
 for i in range(5):pulled.append(i);yield i
it=chunked(source(),2);assert next(it)==[0,1] and pulled==[0,1]
errors=[]
def fn(xs):
 if 2 in xs:raise ValueError('bad')
 return sum(xs)
r,s=run_batches(range(5),fn,2,on_error=lambda xs,e:errors.append(list(xs)))
assert r==[1,None,4] and (s.processed,s.failed)==(2,1) and errors==[[2,3]]
''',
'e18':'''from ttlcache import Cache
clock=[10];c=Cache(default_ttl=3,get_clock=lambda:clock[0]);c.put('a',7);clock[0]=13
assert c.get('a') is None and 'a' not in c and len(c)==0
assert c.get_or_set('a',lambda:9)==9 and c.get('a')==9
''',
'e19':'''from webhook import Processor
p=Processor();calls=[]
def bad(e):calls.append(e);raise ValueError('retry')
try:p.process('x',bad);assert False
except ValueError:pass
assert not p.seen('x');assert p.process('x',lambda e:17)=={'ok':True,'duplicate':False}
assert p.process('x',bad)=={'ok':True,'duplicate':True} and calls==['x'] and p.result('x')==17
''',
'e20':'''from drain import drain
class Source:
 def __init__(self):self.closed=False;self.n=0
 def __iter__(self):yield 1;yield 2
 def close(self):self.closed=True
s=Source();g=drain(s);assert next(g)==1;g.close();assert s.closed
''',
'e21':'''from depgraph import Graph
x=Graph();x.add_module('a',provides=['sym']);x.add_module('b',requires=['sym'],provides=['mid']);x.add_module('c',requires=['mid']);x.add_module('d')
assert x.invalidate('sym')=={'a','b','c'} and set(x.to_json())=={'d'}
''',
'e22':'''from shard import Worker
import tempfile,os
class Model:
 def __init__(self):self.calls=[]
 def infer(self,text):self.calls.append(text);return 'value:'+text
with tempfile.TemporaryDirectory() as d:
 m=Model();Worker(m,['red','blue'],d,checkpoint_every=1).run();assert m.calls==['red','blue']
 os.unlink(os.path.join(d,'blue.txt'));n=Model();w=Worker(n,['red','blue'],d);w.run();assert n.calls==['blue'] and w.total_inferred==1
''',
'e23':'''from cfgx import merge,DROP,freeze
base={'x':{'a':1,'b':2},'items':[1,2]};layer={'x.a':DROP,'items':[2,3]}
r=merge(base,layer,lists='unique');assert r=={'x':{'b':2},'items':[1,2,3]} and base['x']['a']==1 and layer['x.a'] is DROP
f=freeze(r)
try:f['x']['b']=4;assert False
except TypeError:pass
''',
'e24':'''from pfsm import Machine,GuardFailed
s={'a':[{'to':'b','guard':lambda **kw:kw.get('ok',False)}],'b':[]};x=Machine('a',s)
try:x.go('b');assert False
except GuardFailed:pass
assert x.state=='a' and x.history==['a'];assert x.go('b',ok=True)=='b'
h=x.history;h.append('bad');assert x.history==['a','b']
'''
}
def validate():
    records=[]
    for t in load_contract_v2_pack('deepswe2')['tasks']:
        probe=PROBES[t['id'].split('-')[0]];ok,detail=refs.run_check(t['kit'],corrected_reference(t['id']),probe,timeout=30)
        records.append(dict(task=t['id'],reference_ok=ok,detail=detail,probe=probe))
        print(t['id'],ok,detail)
    (ROOT/'results/matched-probe-selftest.json').write_text(json.dumps(records,indent=2)+'\n')
    assert all(r['reference_ok'] for r in records)
def audit(path):
    m=json.loads(Path(path).read_text());tasks={t['id']:t for t in load_contract_v2_pack('deepswe2')['tasks']};records=[]
    for c in m['campaigns']:
        d=json.loads((ROOT/'results'/f"{c['tag']}.json").read_text());answers={a['id']:a['answer'] for a in map(json.loads,(ROOT/'results'/f"{c['tag']}.answers.jsonl").read_text().splitlines())}
        for r in d['targets'][c['target']]['rows']:
            task=tasks[r['task']];probe=PROBES[r['task'].split('-')[0]];ok,detail=refs.run_check(task['kit'],extract_files(answers[r['id']]),probe,timeout=30)
            records.append(dict(campaign=c['tag'],task=r['task'],raw_status=r['status'],probe_ok=ok,detail=detail,probe=probe))
    out=ROOT/'results'/f"{m['prefix']}.probes.json";out.write_text(json.dumps(records,indent=2)+'\n');print(out)
if __name__=='__main__':validate() if len(sys.argv)==1 else audit(sys.argv[1])
