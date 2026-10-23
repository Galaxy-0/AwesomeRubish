"""Read-only renderer parameter discovery for the locally owned 11.3.0 dump."""

import argparse
import hashlib
import json
import re
import struct

import lz4.block
import numpy as np
from rl.demo.build_host import ROOT
from rl.demo.capture import safe_out
from tools.byml import read
from tools.stage_collision import unpack


def research(out):
    out = safe_out(out)
    out.mkdir(exist_ok=False, parents=True)
    path = ROOT / "work/data/v720896/ExeFS/main"
    raw = path.read_bytes()
    flags = struct.unpack_from("<I", raw, 12)[0]
    segments = [struct.unpack_from("<III", raw, 16 + i * 16) for i in range(3)]
    compressed = struct.unpack_from("<III", raw, 96)
    image = bytearray(segments[2][1] + segments[2][2])
    for i, (start, offset, size) in enumerate(segments):
        part = raw[start : start + compressed[i]]
        image[offset : offset + size] = (
            lz4.block.decompress(part, uncompressed_size=size)
            if flags >> i & 1
            else part
        )
    # ADRP + ADD candidates only; inspect the reported functions before any use.
    _, text_offset, text_size = segments[0]
    words = np.frombuffer(image[text_offset : text_offset + text_size], "<u4")
    address = np.flatnonzero((words & 0x9F000000) == 0x90000000)
    ins = words[address].astype(np.int64)
    immediate = ((ins >> 29) & 3) | (((ins >> 5) & 0x7FFFF) << 2)
    immediate = np.where(immediate & (1 << 20), immediate - (1 << 21), immediate)
    pages = ((address * 4 + text_offset) & ~0xFFF) + (immediate << 12)
    strings = []
    for match in re.finditer(rb"[\x20-\x7e]{5,}", image):
        if not any(
            k in match.group()
            for k in [
                b"ResolutionModeController",
                b"FrameBufferBase3DRenderScale",
                b"FrameBufferFormat3D",
            ]
        ):
            continue
        target = match.start()
        refs = []
        for i in address[pages == (target & ~0xFFF)]:
            reg = int(words[i] & 31)
            for j in range(int(i) + 1, min(int(i) + 9, len(words))):
                value = int(words[j])
                if (
                    value & 0xFFC00000 == 0x91000000
                    and (value >> 5) & 31 == reg
                    and (value >> 10) & 0xFFF == target & 0xFFF
                ):
                    refs.append(hex(text_offset + j * 4))
        strings.append(
            dict(
                offset=hex(target),
                text=match.group().decode(),
                adrp_add_candidates=refs,
            )
        )
    boot = ROOT / "work/data/v720896/RomFS/Pack/Bootup.Nin_NX_NVN.pack.zs"
    pack = unpack(boot)
    key = "Gyml/MiniMap.game__gfx__parameter__SpecialEnvParamHolder.bgyml"
    result = dict(
        scope="read-only names/ADRP references; none is a qualified gameplay scale setter",
        build="11.3.0 / main 28c4287aee36f7499da60f3e68b54c70",
        source_sha256={
            str(path.relative_to(ROOT)): hashlib.sha256(raw).hexdigest(),
            str(boot.relative_to(ROOT)): hashlib.sha256(boot.read_bytes()).hexdigest(),
        },
        strings=strings,
        native_scale_example=read(pack[key]),
        limitation="MiniMap has a native .65 scale effect, not proof it can be applied to normal play; constructor/deserializer refs are not rebuild/apply entrypoints",
    )
    (out / "research.json").write_text(json.dumps(result, indent=2) + "\n")
    print(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    research(p.parse_args().out)
