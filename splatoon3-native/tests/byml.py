"""Read the little-endian BYML tables already present in the local game dump."""
import struct


def read(data):
    if data[:2] != b'YB':
        raise ValueError('expected little-endian BYML')
    keys, strings, root = struct.unpack_from('<III', data, 4)

    def u24(offset):
        return int.from_bytes(data[offset:offset + 3], 'little')

    def string_table(offset):
        if not offset:
            return []
        if data[offset] != 0xc2:
            raise ValueError('expected BYML string table')
        offsets = struct.unpack_from('<' + 'I' * u24(offset + 1), data, offset + 4)
        return [data[offset + i:data.index(0, offset + i)].decode('utf-8') for i in offsets]

    key_table, text_table = string_table(keys), string_table(strings)

    def value(kind, raw):
        if kind == 0xa0:
            return text_table[raw]
        if kind in (0xc0, 0xc1):
            return node(raw)
        if kind == 0xd0:
            return bool(raw)
        if kind == 0xd1:
            return struct.unpack('<i', struct.pack('<I', raw))[0]
        if kind == 0xd2:
            return struct.unpack('<f', struct.pack('<I', raw))[0]
        if kind == 0xd3:
            return raw
        if kind in (0xd4, 0xd5, 0xd6):
            return struct.unpack_from({0xd4: '<q', 0xd5: '<Q', 0xd6: '<d'}[kind], data, raw)[0]
        if kind == 0xff:
            return None
        raise ValueError(f'unsupported BYML type: {kind:#x}')

    def node(offset):
        kind, count = data[offset], u24(offset + 1)
        if kind == 0xc0:
            start = (offset + 4 + count + 3) & ~3
            return [value(data[offset + 4 + i], struct.unpack_from('<I', data, start + i * 4)[0])
                    for i in range(count)]
        if kind == 0xc1:
            return {key_table[u24(offset + 4 + i * 8)]:
                    value(data[offset + 7 + i * 8], struct.unpack_from('<I', data, offset + 8 + i * 8)[0])
                    for i in range(count)}
        raise ValueError(f'unsupported BYML node: {kind:#x}')

    return node(root)
