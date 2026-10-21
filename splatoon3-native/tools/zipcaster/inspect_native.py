#!/usr/bin/env python3
"""Extract a private NSO image and verify 11.3.0 D2B static field evidence.

Only hashes, numeric offsets and type names are printed. Image stays under work/.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import lz4.block
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM

ROOT=Path(__file__).resolve().parents[2]
BUILD='28c4287aee36f7499da60f3e68b54c70'
FIELDS={
    'SuperHook':dict(type_name='spl::PlayerSubActionSpSuperHook',vtable=0x5d3e588,
        type_getter=0x2ad8a60,size_getter=0x2ad8a6c,size=0x3b18,owner=0x3af0,
        phase=0x40,position=0x98,normal_local=0xa4,normal_world_cached=0x3a9c,
        actor_pointer=0x88,actor_id=0x3948,actor_world_matrix=0xd8),
    'WeaponSpSuperHook':dict(type_name='spl::WeaponSpSuperHook',vtable=0x5d86220,
        type_getter=0x3191a40,size=0x5c0,hook_link=0x80),
    'PlayerArmor':dict(type_name='spl::PlayerArmor',vtable=0x5d2fc60,
        type_getter=0x281ef6c,size=0xf40,hook_link=0x3ae8,flags=0x30,hp=0x90),
    'PlayerCollision':dict(type_name='spl:PlayerCollision',vtable=0x5d31a20,
        type_getter=0x290acb8,storage_link=0x11cc0,mask=0x21d),
}


def main(args):
    source=args.nso.read_bytes();assert source[:4]==b'NSO0'
    assert source[0x40:0x50].hex()==BUILD
    flags=struct.unpack_from('<I',source,0xc)[0];segments=[]
    for i,header in enumerate((0x10,0x20,0x30)):
        file_offset,memory_offset,size=struct.unpack_from('<III',source,header)
        stored=struct.unpack_from('<I',source,0x60+4*i)[0]
        data=source[file_offset:file_offset+stored]
        if flags&(1<<i):data=lz4.block.decompress(data,uncompressed_size=size)
        assert len(data)==size;segments.append((memory_offset,data))
    image=bytearray(max(offset+len(data)for offset,data in segments))
    for offset,data in segments:image[offset:offset+len(data)]=data
    dis=Cs(CS_ARCH_ARM64,CS_MODE_ARM)
    from decode_sensors import native_type
    for label,fields in FIELDS.items():
        recovered=native_type(struct.pack('<Q',fields['vtable']+1),1,image)
        assert recovered['type_name']==fields['type_name'],(label,recovered)
        assert int(recovered['type_getter_offset'],16)==fields['type_getter']
    assert image[0x2ae101c:0x2ae1020].hex()=='ff0304d1'
    assert image[0x3192a20:0x3192a24].hex()=='fd7bbca9'
    proof={hex(address):[f'{ins.mnemonic} {ins.op_str}'for ins in dis.disasm(image[address:address+length],address)]
           for address,length in [(0x2ad8a6c,12),(0x2adc780,0xc0),(0x281ef80,0x30),(0x2913a78,0x30)]}
    assert ROOT/'work' in args.image.resolve().parents,'private image must stay under work/'
    args.image.parent.mkdir(parents=True,exist_ok=True);args.image.write_bytes(image)
    print(json.dumps(dict(build_id=BUILD,nso_sha256=hashlib.sha256(source).hexdigest(),
        image_sha256=hashlib.sha256(image).hexdigest(),fields=FIELDS,static_instructions=proof),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--nso',type=Path,default=ROOT/'work/data/v720896/ExeFS/main')
    p.add_argument('--image',type=Path,required=True)
    main(p.parse_args())
