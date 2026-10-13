#!/usr/bin/env python3
"""Capture read-only readiness provenance; no inference requests."""
import json,subprocess,time,urllib.request,sys
from pathlib import Path
path=Path(sys.argv[1]);prefix=path.stem.removesuffix('.manifest');seen=set()
def post(port,route,body):
    request=urllib.request.Request(f'http://127.0.0.1:{port}{route}',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(request,timeout=10))
while True:
    try:m=json.loads(path.read_text())
    except (ValueError,OSError):time.sleep(10);continue
    for c in m['campaigns']:
        if c['tag'] in seen:continue
        port=18080 if c['lane']=='qwen27b' else 18081
        record={'campaign':c['tag'],'models':None,'reasoning':{},'gpu':subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.used','--format=csv'],capture_output=True,text=True).stdout,'amd_memory':{str(p):p.read_text().strip() for p in Path('/sys/class/drm').glob('card*/device/mem_info_vram_used')}}
        try:
            record['models']=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models',timeout=5))
            for effort in ['low','medium','xhigh']:
                b={'messages':[{'role':'user','content':'Reply ready'}],'chat_template_kwargs':{'reasoning_effort':effort},'add_generation_prompt':True}
                record['reasoning'][effort]=post(port,'/apply-template' if port==18080 else '/tokenize',b)
            if port==18080:
                assert 'Reasoning effort is set to xhigh' not in record['reasoning']['medium']['prompt']
                assert 'Reasoning effort is set to xhigh' in record['reasoning']['xhigh']['prompt']
            else:assert record['reasoning']['medium']['count']<record['reasoning']['xhigh']['count']
            record['medium_verified']=True
        except Exception as e:record['error']=repr(e)
        (path.parent/f"{c['tag']}.readiness.json").write_text(json.dumps(record,indent=2)+'\n');seen.add(c['tag'])
    if m['status'] in ('complete','failed'):break
    time.sleep(10)
