# dis.py <nso> <hexaddr> [before] [after]: disassemble around a module offset of an NSO (decompressed in memory)
import sys, struct, lz4.block
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
d = open(sys.argv[1], 'rb').read(); flags = struct.unpack_from('<I', d, 0xc)[0]
segs = [struct.unpack_from('<III', d, 0x10 + i * 0x10) for i in range(3)]; csz = struct.unpack_from('<III', d, 0x60)
img = bytearray(segs[2][1] + segs[2][2])
for i, (fo, mo, sz) in enumerate(segs):
    raw = d[fo:fo + csz[i]]
    img[mo:mo + sz] = lz4.block.decompress(raw, uncompressed_size=sz) if flags & (1 << i) else raw
a = int(sys.argv[2], 16); b4 = int(sys.argv[3]) if len(sys.argv) > 3 else 16; af = int(sys.argv[4]) if len(sys.argv) > 4 else 4
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
for x in md.disasm(bytes(img[a - 4 * b4:a + 4 * af]), a - 4 * b4): print(f'{"=>" if x.address == a else "  "} {x.address:8x}  {x.mnemonic:8} {x.op_str}')
