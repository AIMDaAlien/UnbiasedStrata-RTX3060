#!/usr/bin/env python3
"""Regrade every final answer in a fresh scratch repository; paired task bootstrap."""
import collections, importlib.util, json, random, statistics, sys, subprocess, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from bench_contract_v2 import load_contract_v2_pack
spec=importlib.util.spec_from_file_location('runner',ROOT/'bench-run.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
def main(path):
    path=Path(path);m=json.loads(path.read_text());tasks={t['id']:t for t in load_contract_v2_pack('deepswe2')['tasks']};data={};audits=[];fingerprints=None
    engine_hashes={}
    launch_arguments={}
    for c in m['campaigns']:
        if 'actual_argv' in c:
            assert launch_arguments.setdefault(c['lane'],c['actual_argv'])==c['actual_argv'], 'Launch arguments changed within repeats'
        if 'engine_sha256' in c:
            assert engine_hashes.setdefault(c['lane'],c['engine_sha256'])==c['engine_sha256'], 'Engine changed within repeats'
        ready=ROOT/'results'/f"{c['tag']}.readiness.json"
        if ready.exists():
            assert json.loads(ready.read_text()).get('medium_verified'), 'Medium reasoning verification failed'
        d=json.loads((ROOT/'results'/f"{c['tag']}.json").read_text());rows=d['targets'][c['target']]['rows']
        assert len(rows)==24 and len({r['task'] for r in rows})==24
        if fingerprints is None:fingerprints=d['fingerprints']
        assert fingerprints==d['fingerprints']
        if 'tasks' in m:
            for task_id,task in tasks.items():
                expected={'task':hashlib.sha256(json.dumps(task,sort_keys=True).encode()).hexdigest(),'message':hashlib.sha256(json.dumps(runner.build_messages(task,True),sort_keys=True).encode()).hexdigest(),'check':hashlib.sha256(task.get('check','').encode()).hexdigest()}
                assert d['fingerprints'][task_id]==expected, 'Frozen suite changed before offline grading'
                assert m['tasks'][task_id]['task_sha256']==expected['task'] and m['tasks'][task_id]['message_sha256']==expected['message']
        answers={a['id']:a['answer'] for a in map(json.loads,(ROOT/'results'/f"{c['tag']}.answers.jsonl").read_text().splitlines())}
        for r in rows:
            ok,total,detail=runner.grade(tasks[r['task']],{'text':answers[r['id']]})
            audits.append(dict(campaign=c['tag'],task=r['task'],ok=ok,total=total,detail=detail,agrees=(ok,total)==(r['ok'],r['total'])))
        data[c['lane'],c['seed']]={r['task']:r for r in rows}
    (ROOT/'results'/f"{m['prefix']}.regrade.json").write_text(json.dumps(audits,indent=2)+'\n')
    assert all(a['agrees'] for a in audits),'Independent regrade mismatch; inspect audit'
    provenance={'analysis_file_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), ROOT/'tools/matched_probes.py', ROOT/'tools/matched_charts.py'] if p.exists()},'campaigns':m['campaigns'], 'fingerprints':fingerprints, 'flash_git_commit':subprocess.check_output(['git','-C','/home/USER/opt/UnbiasedStrata','rev-parse','HEAD'],text=True).strip()}
    stamp=m['prefix'].removeprefix('qwen27b-flash-matched-')
    for c in m['campaigns']:
        unit=f"bench-matched-{c['lane']}-{c['seed']}-{stamp}"
        log=subprocess.run(['journalctl','--user','-u',unit,'--no-pager'],capture_output=True,text=True).stdout
        (ROOT/'results'/f"{c['tag']}.server.log").write_text(log)
    (ROOT/'results'/f"{m['prefix']}.provenance.json").write_text(json.dumps(provenance,indent=2)+'\n')
    seeds=[40,41,42];ids=sorted(tasks);delta=[statistics.mean(int(data['flash',s][i]['status']=='pass')-int(data['qwen27b',s][i]['status']=='pass') for s in seeds) for i in ids]
    rng=random.Random(20261012);samples=sorted(statistics.mean(rng.choices(delta,k=24))*24 for _ in range(20000))
    mean_scores={lane:statistics.mean(sum(data[lane,seed][i]['status']=='pass' for i in ids) for seed in seeds) for lane in ['qwen27b','flash']}
    lead=f"Flash averaged {mean_scores['flash']:.2f}/24 complete-task passes versus Qwen's {mean_scores['qwen27b']:.2f}/24. The historical 27B advantage was not observed in the corrected comparison. The paired task-bootstrap 95% interval for Flash minus Qwen is [{samples[499]:+.2f}, {samples[19499]:+.2f}] passes; it includes zero."
    lines=['# Matched Qwen 27B versus Flash DeepSWE2','', lead, '', 'Three repeats per model, paired seeds 40–42; 24 distinct synthetic repository tasks. Frozen contract-v2, source included, hidden checks excluded, medium reasoning, temperature zero, matched budgets and escalation. Request latency includes all escalation attempts; length finishes count every attempt, including escalated ones. Repository grading exposes one binary checker per task, so partial-check totals have no within-task resolution.','', '| Model / seed | Complete | Hard | Partial checks | Request errors | Empty finals | Length finishes | Median seconds | Median tokens/s | Runtime seconds |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for c in m['campaigns']:
        rows=list(data[c['lane'],c['seed']].values());answers={a['id']:a['answer'] for a in map(json.loads,(ROOT/'results'/f"{c['tag']}.answers.jsonl").read_text().splitlines())};speed=[r['decode_ts'] for r in rows if r.get('decode_ts')]
        lines.append(f"| {c['lane']} / {c['seed']} | {sum(r['status']=='pass' for r in rows)}/24 | {sum(r['status']=='pass' for r in rows if r['tier']=='t4')}/14 | {sum(r['ok'] for r in rows)}/{sum(r['total'] for r in rows)} | {sum(r['detail'].startswith('req-error') for r in rows)} | {sum(not answers[r['id']].strip() for r in rows)} | {sum(h.get('finish_reason')=='length' for r in rows for h in r.get('attempt_history',[r]))} | {statistics.median(sum(h['wall_s'] for h in r.get('attempt_history',[r])) for r in rows):.1f} | {format(statistics.median(speed),'.1f') if speed else 'n/a'} | {c['wall_s']:.1f} |")
    lines += ['', 'Local configurations:', '', '- Qwen: Swift Qwen3.8 27B Q5_K_M, llama.cpp build 10809, RX 9060 XT plus RTX 3060, context 131,072, q4_0 KV, MTP n=2.', '- Flash: Qwen3.8-Flash-Next GSQ-RCO IQ3_XXS, UnbiasedStrata, RTX 3060 plus CPU with 12 threads, context 196,608, int8 KV with a 32,768-token resident window, speculation 4. Actual executable hashes and arguments are retained in the manifest.']
    lines += ['', 'Historical context: [oct1-dsw2-med.json](oct1-dsw2-med.json) recorded Qwen 7/24 versus Flash 5/24 on the legacy suite. The later Strata legacy repeats scored 5/24 and 7/24. These are background results, not pooled into the corrected matched comparison.']
    lines+=['',f"Mean paired advantage (Flash minus Qwen): {statistics.mean(delta)*24:.2f} complete tasks per run; task-ID bootstrap 95% interval [{samples[499]:.2f}, {samples[19499]:.2f}]. Repeats are clustered within tasks, not treated as independent problems.",'']
    advantage=statistics.mean(delta)*24
    lines += [f"The historical 27B advantage {'survives in the observed mean on this corrected suite' if advantage<0 else 'does not survive in the observed mean on this corrected suite'}. {'The task-level interval includes zero, so these 24 tasks do not resolve a reliable advantage.' if samples[499]<=0<=samples[19499] else 'The task-level bootstrap interval excludes zero; generalization beyond this synthetic suite remains untested.'}", '']
    for lane in ['qwen27b','flash']:
        hard_means=[sum(data[lane,s][i]['status']=='pass' for i in ids if tasks[i]['tier']=='t4') for s in seeds]
        all_rows=[data[lane,seed][i] for seed in seeds for i in ids]
        latency=statistics.median(sum(h['wall_s'] for h in r.get('attempt_history',[r])) for r in all_rows)
        speeds=[r['decode_ts'] for r in all_rows if r.get('decode_ts')]
        runtime=sum(c['wall_s'] for c in m['campaigns'] if c['lane']==lane)
        lines.append(f"{lane}: pooled median request latency {latency:.1f}s; pooled median decode {statistics.median(speeds) if speeds else 0:.1f} tokens/s; total scored-campaign runtime {runtime/60:.1f} minutes.")
        lines.append(f"{lane}: mean hard-tier passes {statistics.mean(hard_means):.2f}/14.")
        counts=[sum(data[lane,s][i]['status']=='pass' for s in seeds) for i in ids];means=[sum(data[lane,s][i]['status']=='pass' for i in ids) for s in seeds]
        lines.append(f"{lane}: mean {statistics.mean(means):.2f}/24; {counts.count(3)} tasks pass all repeats, {counts.count(0)} fail all repeats, {sum(c in (1,2) for c in counts)} vary.")
    lines+=['','Paired outcomes by seed:','']
    for s in seeds:
        wins=sum(data['qwen27b',s][i]['status']=='pass' and data['flash',s][i]['status']!='pass' for i in ids);losses=sum(data['flash',s][i]['status']=='pass' and data['qwen27b',s][i]['status']!='pass' for i in ids)
        lines.append(f'- {s}: Qwen wins {wins}, Flash wins {losses}, ties {24-wins-losses}.')
    disagreements=[i for i in ids if any((data['qwen27b',s][i]['status']=='pass') != (data['flash',s][i]['status']=='pass') for s in seeds)]
    lines += ['', 'Paired seeds 40, 41 and 42 were sent and recorded for every scored request. At temperature zero the Strata frontend selects greedy decoding and does not forward a random seed to the engine; repeat differences should not be described as seed-driven sampling variance.']
    lines += ['', 'Tasks with a paired disagreement: '+', '.join(disagreements)+'. All are included in both regrading and the focused probe audit.']
    lines += ['', f"Exact fixtures and executed checker code: [{m['prefix']}.suite.json]({m['prefix']}.suite.json). Engine/source provenance and hardware metadata are retained beside the raw campaign files."]
    lines+=['','All 144 final answers were independently materialized and regraded in fresh scratch repositories. Full responses and every escalation attempt remain in campaign artifacts. Focused behavioral audit is recorded separately.','', 'This compares local configurations. Q5_K_M versus IQ3_XXS quantization, llama.cpp versus Strata, differing context/KV/speculation and GPU allocation confound capability and speed. It cannot establish hosted frontier parity or performance beyond these 24 tasks. No best-of-three score is used.', '',f"Manifest: [{path.name}]({path.name}); independent grading: [{m['prefix']}.regrade.json]({m['prefix']}.regrade.json)."]
    from matched_probes import audit
    audit(path)
    probes=json.loads((ROOT/'results'/f"{m['prefix']}.probes.json").read_text())
    lines += ['', 'Focused public-API probes ran symmetrically on all 144 saved solutions. Each probe covers selected behavior, so passing it does not override a failure in the full checker. Their results are separate from raw grading:', f"[{m['prefix']}.probes.json]({m['prefix']}.probes.json)."]
    lines += ['', '| Disagreement task | Qwen seeds 40/41/42 | Flash seeds 40/41/42 | Recorded failure evidence |', '|---|---|---|---|']
    for task_id in disagreements:
        patterns={lane:'/'.join('P' if data[lane,seed][task_id]['status']=='pass' else 'F' for seed in seeds) for lane in ['qwen27b','flash']}
        evidence=sorted({data[lane,seed][task_id]['detail'] for lane in ['qwen27b','flash'] for seed in seeds if data[lane,seed][task_id]['status']!='pass'})
        evidence='; '.join(evidence).replace('|','/').replace('\n',' ')
        lines.append(f"| {task_id} | {patterns['qwen27b']} | {patterns['flash']} | {evidence} |")
    lines.append('')
    for lane in ['qwen27b','flash']:
        answers_by_seed={}
        for c in m['campaigns']:
            if c['lane']==lane:
                answers_by_seed[c['seed']]={a['id'].split('/',1)[1]:a['answer'] for a in map(json.loads,(ROOT/'results'/f"{c['tag']}.answers.jsonl").read_text().splitlines())}
        identical=sum(len({answers_by_seed[seed][i] for seed in seeds})==1 for i in ids)
        lines.append(f"- {lane}: {identical}/24 tasks have byte-identical final answers across all three repeats.")
        campaign_tags={c['tag'] for c in m['campaigns'] if c['lane']==lane}
        selected=[p for p in probes if p['campaign'] in campaign_tags]
        lines.append(f"- {lane}: {sum(p['probe_ok'] is True for p in selected)}/72 probe passes; {sum(p['raw_status']=='pass' and p['probe_ok'] is not True for p in selected)} raw passes fail the additional probe.")
    lines += ['', 'Audit probe revisions: early e1/e8 assumptions and final e3/e20 input assumptions were corrected to match the public API contracts. Superseded probe records are retained; the frozen suite and raw campaign scores were unchanged. No offline score correction was applied.']
    chart_script=ROOT/'tools/matched_charts.py'
    if chart_script.exists():
        subprocess.run([str(ROOT/'tools/venv/charts/bin/python'),str(chart_script),str(path)],check=True)
        lines += ['', f"![Mean capability, paired uncertainty and task-level deltas]({m['prefix']}.deltas.png)", '', f"[Delta chart SVG]({m['prefix']}.deltas.svg) · [Chart data]({m['prefix']}.chart-data.json)", '', f"![Capability versus latency for the local configurations]({m['prefix']}.tradeoff.png)", '', f"[Trade-off chart SVG]({m['prefix']}.tradeoff.svg)"]
    (ROOT/'results'/f"{m['prefix']}.report.md").write_text('\n'.join(lines)+'\n')
if __name__=='__main__':main(sys.argv[1])
