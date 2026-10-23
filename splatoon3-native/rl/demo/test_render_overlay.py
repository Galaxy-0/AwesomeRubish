"""Authored format fixtures, no game resources: scalar isolation and Zstd size."""

from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from rl.demo.render_overlay import compress_native, patch_leaf


def fixture():
    raw = bytearray(68)
    struct.pack_into("<2sHIII", raw, 0, b"YB", 3, 16, 0, 48)
    raw[16:20] = bytes([0xC2, 2, 0, 0])
    struct.pack_into("<III", raw, 20, 16, 23, 29)
    raw[32:45] = b"Enable\0Level\0"
    raw[48:52] = bytes([0xC1, 2, 0, 0])
    raw[52:56] = bytes([0, 0, 0, 0xD0])
    struct.pack_into("<I", raw, 56, 1)
    raw[60:64] = bytes([1, 0, 0, 0xD2])
    struct.pack_into("<f", raw, 64, 0.5)
    return bytes(raw)


class OverlayTests(unittest.TestCase):
    def test_scalar_changes_only_its_payload(self):
        raw = fixture()
        patched, old = patch_leaf(raw, ["Enable"], False)
        self.assertIs(old, True)
        self.assertEqual(
            [i for i, (a, b) in enumerate(zip(raw, patched)) if a != b], [56]
        )
        patched, old = patch_leaf(raw, ["Level"], 0.0)
        self.assertEqual(old, 0.5)
        self.assertEqual(patched[:64], raw[:64])

    def test_unknown_or_mistyped_parameter_is_rejected(self):
        raw = fixture()
        with self.assertRaises(KeyError):
            patch_leaf(raw, ["Missing"], False)
        with self.assertRaises(AssertionError):
            patch_leaf(raw, ["Enable"], 0.25)

    @unittest.skipUnless(shutil.which("zstd"), "existing local zstd required")
    def test_embedded_size_for_native_allocation(self):
        raw = b"Authored diagnostic format fixture.\n" * 100
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "fixture.zs"
            compress_native(raw, target)
            data = target.read_bytes()
            self.assertEqual(data[:4], b"\x28\xb5\x2f\xfd")
            flag = data[4]
            single = bool(flag & 32)
            offset = 5 + (0 if single else 1) + [0, 1, 2, 4][flag & 3]
            size_bytes = [int(single), 2, 4, 8][flag >> 6]
            self.assertGreater(
                size_bytes, 0, "unknown content size crashes native allocation"
            )
            size = int.from_bytes(data[offset : offset + size_bytes], "little") + (
                256 if size_bytes == 2 else 0
            )
            self.assertEqual(size, len(raw))
            self.assertEqual(subprocess.check_output(["zstd", "-dc", str(target)]), raw)


if __name__ == "__main__":
    unittest.main()
