"""Finite material-filtered graph and reproducible beam search (no native calls)."""
import argparse,json,math,sys,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from geometry import ROOT,IndexedMesh
from model_v2 import Config,hook_path
from tools.zipcaster.surfaces import load_surfaces
from search_v2 import write,sha

def beam(args):
    started=time.monotonic();coarse=json.loads(args.coarse.read_text());maps=[];cfg=Config()
    for m in coarse['maps']:
        ordered=sorted(m['rows'],key=lambda r:-r['heuristic_score']);nodes=[];seen=set()
        for r in ordered:
            if r['id']not in seen:nodes.append(r);seen.add(r['id'])
            if len(nodes)==args.nodes:break
        tri,_,_,attrs=load_surfaces(ROOT/f'work/arena/maps/{m["id"]}')
        keep=[i for i,a in enumerate(attrs)if'SplPlayerSuperHookCheck'not in a['col_disable_flags']]
        mesh=IndexedMesh(tri[keep]);links={str(i):[]for i in range(len(nodes))};starts={}
        def legal(start,b):
            eye=np.array(start)+[0,1.1,0];anchor=np.array(b['anchor']);d=np.linalg.norm(anchor-eye)
            return 3<=d<=35 and mesh.clear(eye,anchor,.12)
        for i,a in enumerate(nodes):
            for j,b in enumerate(nodes):
                if i!=j and legal(a['attach'],b):links[str(i)].append(j)
        sequences=[]
        for region,start in m['starts'].items():
            starts[region]=[i for i,n in enumerate(nodes)if legal(start,n)]
            live=[((),0.)]
            for depth in range(args.depth):
                expanded=[]
                for sequence,_ in live:
                    options=starts[region]if not sequence else links[str(sequence[-1])]
                    for j in options:
                        if j in sequence:continue
                        seq=(*sequence,j);path,events=hook_path(start,[nodes[k]['anchor']for k in seq],[nodes[k]['attach']for k in seq],cfg,ground_landings=[nodes[k]['landing']for k in seq])
                        if path is None:continue
                        arrival=next(e['frame']for e in events if e['event']=='开始蓄力');terminal=nodes[j]
                        exposure=float(np.mean([nodes[k]['old_exposure']for k in seq]));score=terminal['heuristic_score']*math.exp(-.003*arrival*exposure)
                        expanded.append((seq,score));sequences.append(terminal|dict(source=start,start_region=region,sequence=[nodes[k]['id']for k in seq],sequence_anchors=[nodes[k]['anchor']for k in seq],sequence_attach=[nodes[k]['attach']for k in seq],sequence_landings=[nodes[k]['landing']for k in seq],beam_heuristic=score,arrival_frame=arrival))
                live=sorted(expanded,key=lambda v:-v[1])[:args.width]
        mult=[s for s in sequences if len(s['sequence'])>1];selected=[];terminals=set()
        for s in sorted(mult,key=lambda r:-r['beam_heuristic']):
            if s['id']in terminals:continue
            terminals.add(s['id']);selected.append(s)
            if len(selected)==args.fine_sequences:break
        maps.append(dict(id=m['id'],stage=m['stage'],nodes=nodes,links=links,start_links=starts,sequences_searched=len(sequences),fine_sequences=selected,geometry_queries=mesh.queries))
        print('BEAM '+m['id']+' '+str(len(nodes))+' nodes '+str(sum(map(len,links.values())))+' edges '+str(len(sequences))+' searched',flush=True)
    out=dict(schema='inklab.d3.beam.v1',calibrated=False,search_complete=False,proof_scope='Best of finite beam candidates only; not global optimum or native certified multi-hook.',coarse_sha256=sha(args.coarse),width=args.width,max_hooks=args.depth,node_limit=args.nodes,maps=maps,seconds=time.monotonic()-started,limits=['Surface set is sampled from static collision, material filtering is not a native bind guarantee.','Only arrived-to-next-hook transitions; never exercise native in-flight R/RL_STALL.','Graph ray is HookCheck material geometry, not Sight geometry.','Beam pruning and node cap can discard the true optimum.','Rehook input cooldown and airborne armor remain uncalibrated; native multi-hook is not validated.'])
    write(args.out,out)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--coarse',type=Path,default=ROOT/'work/d3/coarse-current.json');p.add_argument('--out',type=Path,default=ROOT/'work/d3/beam.json');p.add_argument('--nodes',type=int,default=48);p.add_argument('--width',type=int,default=12);p.add_argument('--depth',type=int,default=3);p.add_argument('--fine-sequences',type=int,default=3);beam(p.parse_args())
