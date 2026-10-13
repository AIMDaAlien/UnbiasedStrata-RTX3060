#!/usr/bin/env python3
"""On-demand local-only export; never edits the vault or publishes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, unquote

NOTES = [
 'Model Benchmarks/2026-10-12 Matched Qwen 27B vs Flash DeepSWE2.md',
 'Model Benchmarks/2026-10-12 Matched Qwen vs Flash — Methods and artifacts.md',
 'Strata RTX 3060 Optimization Showcase.md',
 'Strata RTX 3060 long-context tuning.md',
 'Strata Bench.md',
]
ASSETS = ['qwen27b-flash-matched-20261012-165802', 'strata-rtx3060-showcase',
 'strata-prefill-20261010', 'strata-expert-20261011T161207Z',
 'strata-qsa-20261011-screen', 'strata-qsa-20261011-stream-assessment']
TEXT = {'.md','.json','.jsonl','.log','.txt','.csv','.svg','.py','.sh','.patch','.jinja','.yml','.yaml'}

def sha(data):
 return hashlib.sha256(data).hexdigest()

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--vault', type=Path, required=True)
 ap.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'docs')
 a=ap.parse_args(); vault=a.vault.resolve(); out=a.output.resolve()
 if out == vault or vault in out.parents:
  ap.error('output must be outside the vault')
 mapping={vault/n:out/'notes'/Path(n).name for n in NOTES}
 for root in ASSETS:
  for f in sorted((vault/'assets'/root).rglob('*')):
   if f.is_file():
    if f.stat().st_size > 20*1024*1024:
     raise ValueError('unexpected large evidence file: '+str(f))
    mapping[f]=out/'assets'/root/f.relative_to(vault/'assets'/root)
 names={Path(n).stem:vault/n for n in NOTES}; records=[]; unresolved=[]
 for src,dst in mapping.items():
  raw=src.read_bytes(); data=raw
  if src.suffix in TEXT:
   text=raw.decode('utf-8')
   if src.name == 'Strata RTX 3060 long-context tuning.md':
    text=re.sub(r'Exclusions: none\..*?(?=Evidence directory:)', '',text,flags=re.S)
   if src.suffix=='.md':
    def wiki(m):
     embed,target=m.group(1),m.group(2); target,_,label=target.partition('|')
     anchor=''
     if '#' in target: target,anchor=target.split('#',1); anchor='#'+anchor.lower().replace(' ','-')
     source=names.get(target) or (vault/target)
     if source not in mapping:
      unresolved.append({'file':str(src.relative_to(vault)),'target':target})
      return label or target
     href=quote(os.path.relpath(mapping[source],dst.parent),safe='/')+anchor
     return ('!' if embed else '')+'['+(label if label and not label.isdigit() else Path(target).stem)+']('+href+')'
    def link(m):
     label,target=m.group(1),m.group(2)
     if target.startswith(('http:','https:','mailto:','#')): return m.group(0)
     path,sep,anchor=unquote(target.strip('<>')).partition('#')
     source=(src.parent/path).resolve()
     if source not in mapping:
      # Vault-root assets are also used in top-level and archived notes.
      source=(vault/path).resolve()
     if source not in mapping:
      unresolved.append({'file':str(src.relative_to(vault)),'target':target})
      return label+' (local-only reference)'
     return '['+label+']('+quote(os.path.relpath(mapping[source],dst.parent),safe='/')+('#'+anchor if sep else '')+')'
    text=re.sub(r'\[([^\]\n]*)\]\(([^)\n]+)\)',link,text)
    text=re.sub(r'(!?)\[\[([^\]]+)\]\]',wiki,text)
   text=text.replace('/home/aim','/home/USER')
   data=text.encode()
  dst.parent.mkdir(parents=True,exist_ok=True); dst.write_bytes(data)
  records.append({'source':str(src.relative_to(vault)),'export':str(dst.relative_to(out)),
    'original_sha256':sha(raw),'exported_sha256':sha(data),'normalized':raw!=data,'bytes':len(data)})
 (out/'export-manifest.json').write_text(json.dumps({'version':'rtx3060-2026-10-12','direction':'on-demand one-way','normalization':'personal home path; wiki and relative links; unrelated desktop handoff omitted; unexported references rendered as text','files':records,'local_only_references':unresolved},indent=2)+'\n')
 print(f'Exported {len(records)} files; {len(unresolved)} unexported references rendered as text')

if __name__=='__main__': main()
