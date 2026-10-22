"""Build-specific static rejection/call-chain checks; no copied native image."""
import argparse,json,struct,sys
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha

def trace(image):
    data=image.read_bytes();cs=Cs(CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN)
    target=struct.unpack_from('<Q',data,0x5c76738+0x248)[0]
    assert target==0x18d5670
    checks={0x18d5670:('mov','w0, #1'),0x18d5674:('ret',''),
        0x19ec6d4:('ldr','x8, [x20]'),0x19ec6dc:('mov','x0, x20'),
        0x19ec6e4:('ldr','x8, [x8, #0x248]'),0x19ec6e8:('blr','x8'),
        0x19ec6ec:('tbz','w0, #0, #0x19ec844'),0x19ec764:('bl','#0x197e390'),
        0x197e580:('bl','#0x197e5b0'),0x197e984:('bl','#0x2fc7ee0'),
        0x1a93190:('sub','sp, sp, #0x170'),0x1a9410c:('ldr','x0, [x19, #0x4f0]'),
        0x1a94124:('bl','#0x1e10b28'),0x1e10b4c:('ldr','w8, [x1, #0x60]!'),
        0x1e10b5c:('str','w21, [x1]'),0x292077c:('add','x0, x0, #0x30'),
        0x2920780:('bl','#0x1e108a8'),0x1e10960:('str','w8, [x19, #0x58]')}
    for address,expected in checks.items():
        ins=next(cs.disasm(data[address:address+4],address));assert(ins.mnemonic,ins.op_str)==expected,(hex(address),ins.mnemonic,ins.op_str)
    return dict(schema='inklab.d4.contact.filter.static.v1',image_sha256=sha(image),source_sha256=sha(__file__),
        checked_addresses=[hex(a)for a in checks],candidate=dict(actor_vtable='0x5c76738',slot='0x248',
        target=hex(target),constant_return=1,reject_target='0x19ec844',
        conclusion='For this captured SaberSlash vtable, this virtual return cannot select the false branch.'),
        registration_chain=['0x19ec764','0x197e390','0x197e5b0','0x2fc7ee0'],
        receiving_candidate=dict(entry='0x1a93190',actor_argument='x1',life_pointer='this+0x4f0',
                                life_submit='0x1e10b28',input_damage_record='x1',apply_bit='w2 bit0'),
        life_layout=dict(player_damage_to_life='0x30',health='Life+0x58',pending='Life+0x60',
                         native_player_damage_vtable='0x5d32218'),
        scope='Static candidate chain only. Runtime success control must prove receiver attribution and Life submission. No function is named LOS from these checks.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image',type=Path,default=ROOT/'work/d2b/main.bin');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('fresh output required')
    a.out.write_text(json.dumps(trace(a.image),indent=2)+'\n')
