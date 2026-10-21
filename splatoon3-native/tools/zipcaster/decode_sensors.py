#!/usr/bin/env python3
"""Decode test-only D2B snapshots. Unknown candidates never become policy fields."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM

SNAP=re.compile(r'D2B_SNAPSHOT frame=(\d+) kind=(\w+) object=(0x[0-9a-f]+) slot=(-?\d+) size=(\d+) data=([0-9a-f]+)')
STATE_NAMES={0:'State::cWait',1:'State::cShot',2:'State::cPreAttack',3:'State::cAttack'}
DIS=Cs(CS_ARCH_ARM64,CS_MODE_ARM)
TYPE_CACHE={}


def u32(data,offset):return struct.unpack_from('<I',data,offset)[0]
def i32(data,offset):return struct.unpack_from('<i',data,offset)[0]
def vector(data,offset):
    values=list(struct.unpack_from('<3f',data,offset))
    return values if all(math.isfinite(v)and abs(v)<1e5 for v in values)else None


def native_type(data,base,image):
    if len(data)<8 or not base or image is None:return {}
    vt=struct.unpack_from('<Q',data)[0]-base
    if not 0<=vt<len(image)-24:return {}
    if vt in TYPE_CACHE:return TYPE_CACHE[vt]
    fn=struct.unpack_from('<Q',image,vt+16)[0]
    if not 0<=fn<82376320:return dict(vtable_offset=hex(vt))
    page=None;address=None
    for ins in DIS.disasm(image[fn:fn+32],fn):
        if ins.mnemonic=='adrp'and ins.op_str.startswith('x0, #'):page=int(ins.op_str.split('#')[1],16)
        elif ins.mnemonic=='adr'and ins.op_str.startswith('x0, #'):address=int(ins.op_str.split('#')[1],16)
        elif ins.mnemonic=='add'and ins.op_str.startswith('x0, x0, #')and page is not None:address=page+int(ins.op_str.split('#')[1],16)
        elif ins.mnemonic=='ret':break
    result=dict(vtable_offset=hex(vt),type_getter_offset=hex(fn))
    if address is not None and 0<=address<len(image):
        raw=image[address:image.find(b'\0',address)]
        if len(raw)<120 and raw.startswith((b'spl:',b'sead::')):result['type_name']=raw.decode()
    TYPE_CACHE[vt]=result;return result


def decode(match,process,base=0,image=None):
    data=bytes.fromhex(match[6]);size=int(match[5])
    if len(data)!=size:raise ValueError('truncated native snapshot')
    result=dict(schema='inklab.d2b.sensor.v1',process=process,native_frame=int(match[1]),
                kind=match[2],object=match[3],slot=int(match[4]),readonly=True)
    if match[2]=='superhook':
        assert size==0x3b18
        state=i32(data,0x40)
        result.update(state_native=state,state_name=STATE_NAMES.get(state),
            state_provenance='11.3.0 registration at main+2ad95b0; integer at object+40',
            position_98_candidate=vector(data,0x98),normal_a4_candidate=vector(data,0xa4),
            vector_b0_candidate=vector(data,0xb0),normal_3a9c_candidate=vector(data,0x3a9c),
            bind_object_id_candidate=u32(data,0x3948),
            phase_flags_candidate=list(data[0x396a:0x3990]),
            tail_words={hex(off):u32(data,off)for off in range(0x3940,0x3ab8,4)},
            linked_components={hex(off):hex(struct.unpack_from('<Q',data,off)[0])for off in range(0x3ac0,0x3b18,8)},
            semantic_status='Native state registration recovered statically; coordinate/flags candidates require controlled native validation.')
    elif match[2]=='damage':result.update(hp_native=i32(data,0x88),raw_flags_30=u32(data,0x30))
    elif match[2]=='surface_matrix':
        values=list(struct.unpack_from('<12f',data));result['matrix_3x4']=values if all(math.isfinite(v)for v in values)else None
    if match[2]!='surface_matrix':result.update(native_type(data,base,image))
    if result.get('type_name')=='spl::PlayerArmor':
        result.update(armor_flags_native=data[0x30],armor_hp_native=i32(data,0x90),
                      armor_raw_word_94=u32(data,0x94),
                      armor_status='Field offsets statically consumed by PlayerArmor; damage-unit/enable interpretation requires live hit controls.')
    if match[2]=='component_11cc0':result['raw_mask_21d']=data[0x21d]
    return result


def main(args):
    args.out.mkdir(parents=True,exist_ok=True);counts={};transitions=[];hashes={}
    image=args.image.read_bytes()if args.image else None
    with (args.out/'sensors.jsonl').open('w')as output:
        for process in (0,1):
            path=args.session/f'player-{process}/host.log';previous=None;base=0
            with path.open(errors='replace')as source:
                for line in source:
                    start=re.search(r'D2B_SENSOR readonly=1 main=(0x[0-9a-f]+)',line)
                    if start:base=int(start[1],16)
                    match=SNAP.search(line)
                    if not match:continue
                    row=decode(match,process,base,image);counts[(process,row['kind'])]=counts.get((process,row['kind']),0)+1
                    if row['kind']=='superhook':
                        signature=(row['state_native'],tuple(row['position_98_candidate']or[]),tuple(row['normal_3a9c_candidate']or[]))
                        if signature!=previous:
                            transitions.append({k:row[k]for k in ['process','native_frame','state_native','state_name','position_98_candidate','normal_3a9c_candidate','bind_object_id_candidate']});previous=signature
                    output.write(json.dumps(row,allow_nan=False,separators=(',',':'))+'\n')
            hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    result=dict(schema='inklab.d2b.reduction.v1',counts={f'{p}:{k}':v for(p,k),v in counts.items()},
                transitions=transitions,host_log_sha256=hashes,closed_run_required_for_final_hashes=True)
    (args.out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(counts=result['counts'],transitions=len(transitions)),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--image',type=Path,help='Optional local decompressed original main for RTTI, never publish it');main(p.parse_args())
