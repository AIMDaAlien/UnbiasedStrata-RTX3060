#!/usr/bin/env python3
"""Smoke an already-started temporary server; never starts or stops production."""
import argparse
import json
import time
from urllib.request import Request,urlopen
from urllib.error import URLError
from pathlib import Path

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--url',default='http://127.0.0.1:18081');ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 def call(path,body=None):
  req=Request(a.url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
  with urlopen(req,timeout=240) as r:return json.load(r)
 started=time.time()
 while True:
  try:
   health=call('/health');break
  except (URLError,TimeoutError):
   if time.time()-started>1200:raise
   time.sleep(5)
 result={'date':'2026-10-12','health':health,'models':call('/v1/models'),'checks':{}}
 req={'messages':[{'role':'user','content':'Compute 6 times 7 and respond with the number.'}],'reasoning_effort':'medium','temperature':0,'max_tokens':2048}
 count=call('/tokenize',req)['count'];r=call('/v1/chat/completions',req);m=r['choices'][0]['message']
 assert '42' in m.get('content',''),r
 assert m.get('reasoning_content'),r
 assert r['usage']['prompt_tokens']==count,(count,r['usage'])
 assert r['choices'][0]['finish_reason']!='length',r
 result['medium_response']=r;result['tokenize_count']=count
 result['checks'].update(readiness=True,medium_reasoning=True,final_content=True,token_count=True)
 tools=[{'type':'function','function':{'name':'lookup_weather','description':'Get the current weather for a city.','parameters':{'type':'object','properties':{'city':{'type':'string'}},'required':['city']}}}]
 req={'messages':[{'role':'user','content':'Call lookup_weather for Boston. Do not guess the weather; use the tool.'}],'tools':tools,'tool_choice':'required','reasoning_effort':'medium','temperature':0,'max_tokens':2048}
 r=call('/v1/chat/completions',req);m=r['choices'][0]['message'];tc=m.get('tool_calls',[]);assert tc,r
 assert tc[0]['function']['name']=='lookup_weather',r
 args=json.loads(tc[0]['function']['arguments']);assert 'boston' in args.get('city','').lower(),r
 result['tool_response']=r
 req['messages'] += [m,{'role':'tool','tool_call_id':tc[0]['id'],'content':'{"temperature_c":18,"condition":"clear"}'}]
 req['tool_choice']='none';r=call('/v1/chat/completions',req);assert r['choices'][0]['message'].get('content'),r
 result['tool_followup']=r;result['checks']['tool_calls']=True
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print('Passed readiness, medium reasoning, final content, token counting and tool round trip')

if __name__=='__main__':main()
