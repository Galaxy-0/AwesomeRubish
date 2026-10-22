"""Measure lossless recipe/value packing. Output stays ignored, not assets."""
import argparse,base64,gzip,json,struct,zlib,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
PROGRAMS=['full-light','light3','light-full','full2'];FAIL=['unreachable-in-declared-graph','dies-before-any-declared-route-can-move-or-kill','no-winning-route-in-declared-model','occupied','unresolved']
def main(a):
 if a.out.exists():raise ValueError('fresh packed output')
 maps=[]
 for name in['Yunohana','District00','Yagara']:
  files=sorted(a.bank.glob(name+'-*.json.gz'));recipes=[];lookup={};states=[];arrays=[];inputs={}
  for p in files:
   d=json.loads(gzip.decompress(p.read_bytes()));q=d['result'];assert d['status']=='complete'and q['search_complete'];g=q['ground_nodes'];values=np.zeros((g,4),np.uint32)
   for row in q['rows']:
    index=row['start']
    if row['probability']==1:
     key=(PROGRAMS.index(row['program']),*row['hooks'])
     if key not in lookup:lookup[key]=len(recipes);recipes.append(key)
     values[index]=[len(FAIL)+lookup[key],round(row['remaining']*1_000_000),row['exposure_frames'],int(row['stealth'])]
    else:values[index,0]=FAIL.index(row['status'])if row['status']in FAIL else 4
   arrays.append(values);states.append([d['enemy_index'],d['heading'],d['speed']]);inputs[str(p.resolve().relative_to(ROOT))]=sha(p)
  raw=np.array(arrays,dtype='<u4').tobytes();compressed=zlib.compress(raw,9);recipejson=json.dumps(recipes,separators=(',',':')).encode();maps.append(dict(map=name,states=states,shape=[len(states),g,4],dtype='<u4',encoding='zlib-base64',values=base64.b64encode(compressed).decode(),recipes=recipes,metrics=dict(queries=len(states),pairs=len(states)*g,recipes=len(recipes),uncompressed_bytes=len(raw),compressed_bytes=len(compressed),recipes_json_bytes=len(recipejson)),source_sha256=inputs))
 out=dict(schema='inklab.d4.packed.v1',maps=maps,failures=FAIL,programs=PROGRAMS,columns=['route-recipe-or-status','remaining-millionths','exposure-frames','stealth-bit'],scope='Complete queried states only. Millionth quantization of remaining budget; route identities lossless. No raw asset geometry or screenshots. Not yet all enemy states.',source_sha256=sha(__file__));a.out.write_text(json.dumps(out,separators=(',',':'))+'\n');print(json.dumps([m['metrics']for m in maps],indent=2));print('PACKED_BYTES',a.out.stat().st_size)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--bank',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
