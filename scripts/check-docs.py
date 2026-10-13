#!/usr/bin/env python3
"""Check local Markdown destinations and exported evidence bytes."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

root=Path(__file__).resolve().parents[1]
errors=[]
for f in [root/'README.md']+[f for f in (root/'docs').rglob('*.md') if 'upstream' not in f.parts]:
 text=f.read_text()
 # Fenced code includes historical literal Markdown examples, not document links.
 text=re.sub(r'```.*?```','',text,flags=re.S)
 if re.search(r'!?\[\[',text): errors.append(str(f)+': unconverted wiki link')
 for target in re.findall(r'\[[^\]\n]*\]\(([^)\n]+)\)',text):
  if target.startswith(('http:','https:','mailto:','#')):continue
  path=unquote(target.strip('<>').split('#')[0])
  if path and not (f.parent/path).exists():errors.append(str(f.relative_to(root))+': missing '+target)
manifest=json.loads((root/'docs/export-manifest.json').read_text())
for row in manifest['files']:
 f=root/'docs'/row['export'];h=hashlib.sha256(f.read_bytes()).hexdigest()
 if h!=row['exported_sha256']:errors.append('checksum mismatch: '+str(f))
 if f.suffix=='.svg' and '<svg' not in f.read_text():errors.append('invalid SVG: '+str(f))
 if f.suffix=='.png' and f.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':errors.append('invalid PNG: '+str(f))
if errors:raise SystemExit('\n'.join(errors))
print(f'Checked local links and {len(manifest["files"])} exported evidence hashes; PNG/SVG signatures valid')
