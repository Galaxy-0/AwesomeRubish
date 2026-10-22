"""Read-only build-specific checks for contact shape construction evidence."""
import argparse
import json
import sys
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha


def inspect(path):
    data = path.read_bytes()
    cs = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    checks = {
        0x17a9048: ('add', 'x8, x27, #0x30'),
        0x17a9154: ('add', 'x8, x28, #0x3c'),
        0x19eb408: ('ldr', 's0, [x22, #0x44]'),
        0x19eb414: ('ldp', 's2, s3, [x23, #0x30]'),
        0x19eb418: ('ldr', 's4, [x23, #0x38]'),
        0x19eb41c: ('fadd', 's0, s0, s4'),
        0x19eb42c: ('str', 's0, [x27, #0xf0]'),
        0x19eb868: ('add', 'x1, x22, #0x3c'),
        0x19eb870: ('bl', '#0x4a6f970'),
        0x19eba28: ('ldr', 's0, [x22, #0x44]'),
        0x19eba34: ('ldp', 's2, s3, [x23, #0x48]'),
        0x19eba44: ('fadd', 's0, s0, s4'),
        0x19ebbf4: ('ldr', 's0, [x22, #0x44]'),
        0x19ebc00: ('ldp', 's2, s3, [x23, #0x54]'),
        0x19ebc10: ('fadd', 's0, s0, s4'),
        0x19ebc28: ('bl', '#0x4a76300'),
        0x19ebd00: ('ldr', 's0, [x28, #0x60]'),
        0x19ebd08: ('bl', '#0x4a761e0'),
        0x4cb7b3c: ('add', 'x2, x20, #0x268'),
        0x4cb7b40: ('add', 'x1, x20, #0x25c'),
        0x4cb7b44: ('bl', '#0x4a85aa4'),
        0x4a85aa4: ('ldr', 'x8, [x1]'),
        0x4a85ab0: ('str', 'x8, [x0, #0x40]'),
        0x4a85ab4: ('ldr', 's0, [x2]'),
        0x4a85af4: ('ldr', 's0, [x2, #0x20]'),
        0x4a85af8: ('str', 's0, [x0, #0x6c]'),
    }
    for address, expected in checks.items():
        instruction = next(cs.disasm(data[address:address+4], address))
        assert (instruction.mnemonic, instruction.op_str) == expected, hex(address)
    assert data[0x4f3b533:0x4f3b533+15] == b'BoxHalfExtents\0'
    assert data[0x4fef1e8:0x4fef1e8+10] == b'BoxCenter\0'
    return dict(schema='inklab.d4.contact.static.v1', image_sha256=sha(path),
                tool_sha256=sha(__file__), checked_addresses=[hex(x) for x in checks],
                parameter_layout=dict(BoxCenter='0x30', BoxHalfExtents='0x3c',
                                      CylinderCenterA='0x48', CylinderCenterB='0x54', CylinderRadius='0x60'),
                local_translation='(0,0,BoxHalfExtents.Z) added to box center and cylinder endpoints',
                engine_rotation_offset='0x268',engine_position_offset='0x25c',
                physics_consumer='main+0x4a85aa4 copies position3/rotation9 into physics interface',
                world_transform_consumer_verified=True,
                limits=['Build-specific read-only static evidence; no copied native instructions/assets in report.',
                        'This does not prove actor rotation, target Body shape, contact timing, or stable hit rate.'])


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--image', type=Path, default=ROOT/'work/d2b/main.bin')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise ValueError('fresh output required')
    a.out.write_text(json.dumps(inspect(a.image), indent=2)+'\n')
