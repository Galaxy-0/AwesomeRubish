"""Read-only current-image RTTI/getter inventory; no game bytes in output repo."""
import argparse,json,struct,hashlib
from pathlib import Path
import numpy as np
def locate(path):
 data=path.read_bytes();w=np.frombuffer(data[:0x4e90000],'<u4');ix=np.flatnonzero((w[:-2]&0x9f000000)==0x90000000);a=w[ix];b=w[ix+1];reg=a&31;valid=((b&0xffc00000)==0x91000000)&((b&31)==reg)&(((b>>5)&31)==reg);ix=ix[valid];a=a[valid];b=b[valid];imm=(((a.astype(np.int64)>>5)&0x7ffff)<<2)|((a>>29)&3);imm=np.where(imm>=0x100000,imm-0x200000,imm);target=((ix*4)&~4095)+(imm<<12)+((b>>10)&4095)
 out=[]
 for token in [b'PlayerCamera',b'BulletSaberHorizontal',b'BulletSaberVertical',b'BulletSaberBase',b'BulletSaber',b'BulletShooterBase']:
  start=0
  while True:
   p=data.find(token+b'\0',start)
   if p<0:break
   start=p+len(token);name_start=data.rfind(b'\0',0,p)+1;getter=[int(i)*4 for i in ix[(target==name_start)&(w[ix+2]==0xd65f03c0)]]
   for g in getter:
    ptr=struct.pack('<Q',g);vrefs=[];pos=0
    while True:
     pos=data.find(ptr,pos)
     if pos<0:break
     if pos%8==0:vrefs.append(hex(pos))
     pos+=1
    out.append(dict(type=token.decode(),string=hex(p),getter=hex(g),getter_vtable_refs=vrefs))
 return dict(image_sha256=hashlib.sha256(data).hexdigest(),rows=out)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--image',type=Path,default=Path('work/d2b/main.bin'));a=p.parse_args();print(json.dumps(locate(a.image),indent=2))
