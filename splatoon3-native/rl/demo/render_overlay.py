"""Private native quality-parameter experiment; never modify the source RomFS.

Patch existing BYML scalar payloads in-place inside SARC, preserving every other
byte and archive offset. These are visual settings, not verified FPS switches.
"""

import argparse
import hashlib
import json
import struct
import subprocess

from rl.demo.capture import safe_out
from rl.demo.build_host import ROOT
from tools.byml import read


def patch_leaf(data, path, value):
    data = bytearray(data)
    assert data[:2] == b"YB"
    keys, _, node = struct.unpack_from("<III", data, 4)
    count = int.from_bytes(data[keys + 1 : keys + 4], "little")
    offsets = struct.unpack_from("<" + "I" * count, data, keys + 4)
    names = [data[keys + q : data.index(0, keys + q)].decode() for q in offsets]
    before = read(data)
    expected = json.loads(json.dumps(before))
    parent = expected
    for k in path[:-1]:
        parent = parent[k]
    old = parent[path[-1]]
    parent[path[-1]] = value
    for depth, key in enumerate(path):
        assert data[node] == 0xC1
        n = int.from_bytes(data[node + 1 : node + 4], "little")
        for i in range(n):
            p = node + 4 + i * 8
            index = int.from_bytes(data[p : p + 3], "little")
            if names[index] == key:
                kind = data[p + 3]
                if depth < len(path) - 1:
                    node = struct.unpack_from("<I", data, p + 4)[0]
                else:
                    if isinstance(value, bool):
                        assert kind == 0xD0
                        struct.pack_into("<I", data, p + 4, int(value))
                    else:
                        assert kind == 0xD2
                        struct.pack_into("<f", data, p + 4, value)
                break
        else:
            raise KeyError(path)
    assert read(data) == expected
    return bytes(data), old


def archive_patch(path, edits):
    archive = bytearray(subprocess.check_output(["zstd", "-dc", str(path)]))
    h = struct.unpack_from("<H", archive, 4)[0]
    data_start = struct.unpack_from("<I", archive, 12)[0]
    count = struct.unpack_from("<H", archive, h + 6)[0]
    names = h + 12 + count * 16 + 8
    changed = []
    for i in range(count):
        _, key, lo, hi = struct.unpack_from("<4I", archive, h + 12 + i * 16)
        start = names + (key & 0xFFFFFF) * 4
        name = archive[start : archive.index(0, start)].decode()
        if name not in edits:
            continue
        old = bytes(archive[data_start + lo : data_start + hi])
        raw = old
        for path, value in edits[name]:
            raw, previous = patch_leaf(raw, path, value)
            changed.append(dict(entry=name, path=path, old=previous, new=value))
        assert len(raw) == len(old)
        archive[data_start + lo : data_start + hi] = raw
    assert len(changed) == sum(map(len, edits.values()))
    return bytes(archive), changed


def compress_native(archive, target):
    # The native loader allocates from the embedded frame content size.
    with target.open("wb") as f:
        subprocess.run(
            ["zstd", "-q", "--no-check", f"--stream-size={len(archive)}", "-c"],
            input=archive,
            stdout=f,
            check=True,
        )


def build(out):
    out = safe_out(out)
    out.mkdir(exist_ok=False, parents=True)
    edits = {
        "Pack/Scene/Vss_Yunohana.pack.zs": {
            "Gyml/Vss_YunohanaDay00.game__gfx__parameter__RenderingDay.bgyml": [
                (["PostEffect", "ColorGrading", "Enable"], False),
                (["PostEffect", "Bloom", "Intensity"], 0.0),
            ]
        },
        "Pack/Bootup.Nin_NX_NVN.pack.zs": {
            "Gyml/Default.game__gfx__parameter__RenderingDay.bgyml": [
                (["PostEffect", "DOFGaussian", "Level"], 0.0),
            ]
        },
    }
    report = dict(
        scope="private visual-quality experiment; native consumption/pass reduction must be measured",
        files={},
    )
    for name, changes in edits.items():
        source = ROOT / "work/data/v720896/RomFS" / name
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        archive, changed = archive_patch(source, changes)
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        compress_native(archive, target)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        report["files"][name] = dict(
            source_sha256=digest,
            overlay_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            changes=changed,
        )
    (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(out)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    build(p.parse_args().out)
