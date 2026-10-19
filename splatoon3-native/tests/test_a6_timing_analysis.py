#!/usr/bin/env python3
"""Reservation/refund counterexample and physical input-window bounds."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from analyze_a6_timing import analyze


class TimingAnalysis(unittest.TestCase):
    def test_refunded_full_reservation_cannot_certify_full_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'player-0').mkdir()
            def packet(frame,ink,form):
                data=bytearray(0x1f0);struct.pack_into('<f',data,0x84,ink);data[0xf8]=form
                return f'RL_STATE frame={frame} sequence=1 data={data.hex()}\n'
            (root/'player-0/host.log').write_text(packet(99,1.,0)+packet(103,.883,1)+packet(139,.948,1))
            path=root/'result.json'
            path.write_text(json.dumps(dict(session=str(root),cases=[dict(kind='surface-charge',hold_frames=5,start_frame=100,release_frame=105)])))
            result=analyze(path)
            self.assertFalse(result['rows'][0]['full_release'])
            self.assertIsNone(result['minimum_observed_full_release']['surface-charge'])
            self.assertEqual(result['rows'][0]['emergence_to_release_bounds'],[2,5])


if __name__=='__main__':unittest.main()
