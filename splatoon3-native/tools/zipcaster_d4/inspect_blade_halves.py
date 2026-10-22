"""Build-specific static guards for shared projectile outward clipping."""
import argparse,json,struct
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN
from tools.zipcaster_d3r.analyze_direction import sha

def inspect(image,parameters):
 b=image.read_bytes();c=Cs(CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN)
 checks={0x19dc934:('cmp','x23, x8'),0x19dc93c:('csel','w28, wzr, w23, lt'),
  0x19dc940:('b.lt','#0x19dc950'),0x19dc94c:('sub','w8, w0, #1'),
  0x19dc984:('str','xzr, [x26]'),0x19dcb0c:('cmp','x21, x8'),
  0x19dcb10:('b.ne','#0x19dcb28'),0x19dcb14:('mov','w8, wzr'),
  0x19dcb18:('sub','w9, w0, #1'),0x19dcb90:('str','xzr, [x25]'),
  0x19d7270:('ldr','w0, [x26, #0x80]'),0x19d7838:('csel','x8, x9, x8, ne')}
 for a,want in checks.items():
  i=next(c.disasm(b[a:a+4],a));assert(i.mnemonic,i.op_str)==want,(hex(a),i.mnemonic,i.op_str)
 for vt in [0x5c75510,0x5c76df0]:assert struct.unpack_from('<Q',b,vt+0x3b8)[0]==0x19dc880
 p=json.loads(parameters.read_text());groups={}
 for k,axis in [('horizontal','X'),('vertical','Y')]:
  q=p[k+'_projectile']['CollisionParam'];core=q['CoreIndex'];o=q['OffsetArray']
  assert len(o)==(5 if k=='horizontal'else 7)
  groups[k]=dict(core=core,negative_indices=list(range(core)),positive_indices=list(range(core+1,len(o))),
   axis=axis,offsets=[x[axis]for x in o],shared_truncation='main+0x19dc880')
 return dict(schema='inklab.d4.blade.halves.static.v1',image_sha256=sha(image),parameters_sha256=sha(parameters),
  source_sha256=sha(__file__),checks=[hex(a)for a in checks],groups=groups,
  arrays={'0x1200':'j<core -> [0,j], otherwise [j,n-1]',
          '0x1280':'j<core -> [0,j], j>core -> [j,n-1], j==core -> all'},
  contact='SaberSlash is a separate class. Captured full compound has Box and Cylinder leaves, not evidence of two independently removed halves.',
  limits=['Native query-array role and cross-array synchronization require runtime witnesses.',
          'Static deletion ranges do not prove continuous-time sphere sweeps reproduce native collision ordering.',
          'No contact140/20 LOS rule, world transform or global optimality certification.'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--image',type=Path,default=Path('work/d2b/main.bin'));p.add_argument('--parameters',type=Path,default=Path('work/a6/parameters.json'));p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert not a.out.exists();a.out.write_text(json.dumps(inspect(a.image,a.parameters),indent=2)+'\n')
