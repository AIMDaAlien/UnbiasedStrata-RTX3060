#!/usr/bin/env python3
"""Export a paired-delta chart and configuration trade-off chart from audited runs."""
import json,random,statistics,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
ROOT=Path(__file__).resolve().parents[1]
COLORS={'qwen27b':'#bd6028','flash':'#167da5'}
NAMES={'qwen27b':'Qwen 27B Q5_K_M','flash':'Flash IQ3_XXS'}
def main(path):
    path=Path(path);m=json.loads(path.read_text());assert len(m['campaigns'])==6
    data={};runs=[]
    for c in m['campaigns']:
        doc=json.loads((path.parent/f"{c['tag']}.json").read_text());rows=doc['targets'][c['target']]['rows'];assert len(rows)==24 and len({r['task'] for r in rows})==24
        data[c['lane'],c['seed']]={r['task']:r for r in rows}
        runs.append(dict(lane=c['lane'],seed=c['seed'],passes=sum(r['status']=='pass' for r in rows),hard_passes=sum(r['status']=='pass' for r in rows if r['tier']=='t4'),latency=statistics.median(sum(h['wall_s'] for h in r['attempt_history']) for r in rows),decode=statistics.median(r['decode_ts'] for r in rows if r.get('decode_ts')),runtime=c['wall_s']))
    ids=sorted(next(iter(data.values())));seeds=[40,41,42]
    deltas={i:statistics.mean(int(data['flash',s][i]['status']=='pass')-int(data['qwen27b',s][i]['status']=='pass') for s in seeds) for i in ids}
    rng=random.Random(20261012);boot=sorted(sum(rng.choices(list(deltas.values()),k=24)) for _ in range(20000));ci=[boot[499],boot[19499]];difference=sum(deltas.values())
    changed=[i for i in ids if any((data['flash',s][i]['status']=='pass')!=(data['qwen27b',s][i]['status']=='pass') for s in seeds)];changed.sort(key=lambda i:(-deltas[i],int(i.split('-')[0][1:])))
    score={lane:statistics.mean(r['passes'] for r in runs if r['lane']==lane) for lane in NAMES}
    chart_data=dict(prefix=m['prefix'],runs=runs,mean_complete=score,flash_minus_qwen=difference,task_bootstrap_95=ci,task_deltas=deltas,distinct_tasks=24,repeats_per_model=3)
    (path.parent/f"{m['prefix']}.chart-data.json").write_text(json.dumps(chart_data,indent=2)+'\n')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','axes.labelcolor':'#24313a','text.color':'#24313a','axes.edgecolor':'#b3bec5','savefig.facecolor':'white'})
    fig=plt.figure(figsize=(13.5,7.5));gs=fig.add_gridspec(2,2,width_ratios=[1,1.55],height_ratios=[1,1],hspace=.55,wspace=.48)
    ax=fig.add_subplot(gs[0,0]);labels=['Complete tasks','Hard-tier tasks'];denoms=[24,14]
    for y,metric in enumerate(['passes','hard_passes']):
        means={lane:statistics.mean(r[metric] for r in runs if r['lane']==lane) for lane in NAMES};q,f=means['qwen27b']/denoms[y],means['flash']/denoms[y]
        ax.plot([q,f],[y,y],color='#a5b4bd',lw=3,zorder=1)
        for lane,value in [('qwen27b',q),('flash',f)]:
            ax.scatter(value,y,s=100,color=COLORS[lane],zorder=3,label=NAMES[lane] if y==0 else None)
            ax.annotate(f"{means[lane]:.2f}/{denoms[y]}",(value,y),xytext=(-3,-20 if lane=='qwen27b' else 14),textcoords='offset points',ha='center',fontsize=10,color=COLORS[lane])
        ax.text(.02,y+.28,f"Flash − Qwen: {means['flash']-means['qwen27b']:+.2f} tasks ({(f-q)*100:+.1f} pp)",fontsize=10)
    ax.set_yticks([0,1],labels);ax.invert_yaxis();ax.set_ylim(1.55,-.45);ax.set_xlim(0,1.03);ax.xaxis.set_major_formatter(PercentFormatter(1));ax.set_xlabel('Mean pass rate across three repeats');ax.set_title('Mean capability',loc='left',pad=16);ax.grid(axis='x',color='#e6ebee');fig.legend(*ax.get_legend_handles_labels(),loc='upper left',bbox_to_anchor=(.06,.085),ncol=2,frameon=False,fontsize=9)
    ax=fig.add_subplot(gs[1,0]);ax.axvline(0,color='#b3bec5',lw=1)
    ax.errorbar(difference,0,xerr=[[difference-ci[0]],[ci[1]-difference]],fmt='o',color=COLORS['flash'],ms=9,capsize=6,lw=3)
    ax.set_yticks([]);ax.set_ylim(-1,1);lo=min(-1,ci[0]-1);hi=max(1,ci[1]+1);ax.set_xlim(lo,hi);ax.set_xlabel('Flash − Qwen complete-task passes per run');ax.set_title('Paired uncertainty across task IDs',loc='left',pad=12);ax.grid(axis='x',color='#e6ebee');ax.text(.02,.88,f"Mean {difference:+.2f}; 95% interval [{ci[0]:+.2f}, {ci[1]:+.2f}]",transform=ax.transAxes,fontsize=10)
    ax.text(.02,.12,'Repeats stay clustered within each task.\n24 distinct tasks, not 144 independent problems.',transform=ax.transAxes,fontsize=9,color='#596c78')
    ax=fig.add_subplot(gs[:,1]);ys=list(range(len(changed)));vals=[deltas[i] for i in changed]
    ax.barh(ys,vals,color=[COLORS['flash'] if v>=0 else COLORS['qwen27b'] for v in vals],height=.55)
    names=[i.split('-',1)[1].replace('-',' ') for i in changed];ax.set_yticks(ys,names);ax.invert_yaxis();ax.axvline(0,color='#7c8d97',lw=1);ax.set_xlim(-1.18,1.85);ax.set_xticks([-1,-.5,0,.5,1]);ax.set_xlabel('Mean paired pass difference per task\nPositive favors Flash; negative favors Qwen');ax.set_title('Which tasks explain the delta?',loc='left',pad=16);ax.grid(axis='x',color='#e6ebee');ax.set_axisbelow(True)
    for y,i in enumerate(changed):
        q=sum(data['qwen27b',s][i]['status']=='pass' for s in seeds);f=sum(data['flash',s][i]['status']=='pass' for s in seeds)
        ax.text(1.08,y,f"Qwen {q}/3 · Flash {f}/3",va='center',fontsize=9)
    ax.text(.01,.985,f"{24-len(changed)} other tasks have identical paired outcomes in all repeats.",transform=ax.transAxes,va='top',fontsize=9,color='#596c78')
    fig.suptitle('Flash versus Qwen 27B — corrected local coding comparison',x=.06,ha='left',fontsize=17,fontweight='bold',y=.99)
    fig.text(.06,.94,'24 synthetic repository tasks · 3 fresh-process repeats per model · medium reasoning · temperature zero',fontsize=10,color='#596c78')
    fig.text(.06,.025,'Different weights, quantization, engines, KV formats and GPU allocation confound model-only conclusions.',fontsize=9,color='#596c78');fig.subplots_adjust(top=.85,bottom=.16,left=.1,right=.96)
    for ext in ['png','svg']:fig.savefig(path.parent/f"{m['prefix']}.deltas.{ext}",dpi=180)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,6.2))
    for lane in NAMES:
        rr=[r for r in runs if r['lane']==lane];xs=[r['latency'] for r in rr];ys=[r['passes']/24 for r in rr]
        ax.scatter(xs,ys,color=COLORS[lane],s=50,alpha=.55)
        for j,r in enumerate(rr):ax.annotate(str(r['seed']),(r['latency'],r['passes']/24),xytext=(7,[-15,2,19][j]),textcoords='offset points',fontsize=9,color=COLORS[lane])
        x=statistics.mean(xs);y=statistics.mean(ys);ax.scatter(x,y,color=COLORS[lane],s=170,marker='D',label=f"{NAMES[lane]} — mean of runs")
        ax.annotate(f"{score[lane]:.2f}/24\n{x:.1f}s mean run median",(x,y),xytext=(-135,20) if lane=='flash' else (16,-40),textcoords='offset points',fontsize=10,color=COLORS[lane],arrowprops={'arrowstyle':'-','color':COLORS[lane]})
    ax.set_xlim(0,max(r['latency'] for r in runs)*1.5);ax.set_ylim(.7,1.035);ax.yaxis.set_major_formatter(PercentFormatter(1));ax.set_xlabel('Run median task-request latency, seconds (lower is better)');ax.set_ylabel('Complete-task pass rate (higher is better)');ax.set_title('Local configuration trade-off: capability versus latency',loc='left',pad=18);ax.grid(color='#e6ebee');ax.legend(loc='lower left',frameon=False,fontsize=9)
    ax.text(.03,.95,'Better direction: upper left\nSmall circles: runs 40, 41, 42 · Diamonds: run means',transform=ax.transAxes,va='top',fontsize=9,color='#596c78');fig.text(.09,.025,'Only these two local configurations are compared. Latency includes every escalation attempt; task-bootstrap uncertainty is in the delta chart.',fontsize=8,color='#596c78');fig.tight_layout(rect=(0,.06,1,1))
    for ext in ['png','svg']:fig.savefig(path.parent/f"{m['prefix']}.tradeoff.{ext}",dpi=180)
    plt.close(fig)
    print(path.parent/f"{m['prefix']}.deltas.png")
if __name__=='__main__':main(sys.argv[1])
