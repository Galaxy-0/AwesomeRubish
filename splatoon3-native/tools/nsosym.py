# nsosym.py <ExeFS dir> mod+0xoff ...: name the exported function containing each module offset (nearest preceding defined dynamic symbol)
import sys, struct, bisect, subprocess, os
import lz4.block
cache = {}
def load(path):
    d = open(path, 'rb').read(); flags = struct.unpack_from('<I', d, 0xc)[0]
    segs = [struct.unpack_from('<III', d, 0x10 + i * 0x10) for i in range(3)]; csz = struct.unpack_from('<III', d, 0x60)
    img = bytearray(segs[2][1] + segs[2][2])
    for i, (fo, mo, sz) in enumerate(segs):
        raw = d[fo:fo + csz[i]]; img[mo:mo + sz] = lz4.block.decompress(raw, uncompressed_size=sz) if flags >> i & 1 else raw
    return bytes(img)
def table(mod):
    if mod not in cache:
        img = load(os.path.join(sys.argv[1], mod)); mod0 = struct.unpack_from('<I', img, 4)[0]; dyn = mod0 + struct.unpack_from('<i', img, mod0 + 4)[0]
        tags = {}
        for i in range(4096):
            t, v = struct.unpack_from('<qQ', img, dyn + i * 16)
            if t == 0: break
            tags.setdefault(t, v)
        st, sr = tags[6], tags[5]; n = (sr - st) // 24; rows = []
        for i in range(1, n):
            nm, info, oth, sh, val, sz = struct.unpack_from('<IBBHQQ', img, st + i * 24)
            if sh and val: rows.append((val, sz, img[sr + nm:img.index(b'\0', sr + nm)].decode('latin1')))
        rows.sort(); cache[mod] = rows
    return cache[mod]
for a in sys.argv[2:]:
    mod, off = a.split('+'); off = int(off, 16); rows = table(mod)
    k = bisect.bisect_right([r[0] for r in rows], off) - 1
    v, sz, nm = rows[k] if k >= 0 else (0, 0, '?')
    dem = subprocess.run(['c++filt', nm], capture_output=True, text=True).stdout.strip()
    print(f'{a}\t{dem}+{off - v:#x}{"" if off < v + sz else " (past end)"}')
