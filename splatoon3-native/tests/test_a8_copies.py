import unittest
from analyze_a8_copies import parse_sources,source_label,classify
from analyze_a8 import actual_copy_reduction


class CopyAttributionTests(unittest.TestCase):
    def test_mode_marker_must_show_consistent_actual_reduction(self):
        self.assertTrue(actual_copy_reduction(['A8_COPY coalesce native_updates=7 copies=2 saved=5'],'coalesce'))
        self.assertTrue(actual_copy_reduction(['A8_COPY scatter native_updates=7 dispatches=1'],'scatter'))
        for row in ('A8_COPY coalesce native_updates=7 copies=7 saved=0','A8_COPY coalesce native_updates=7 copies=2 saved=4','A8_COPY scatter native_updates=7 dispatches=1'):
            self.assertFalse(actual_copy_reduction([row],'coalesce'))
    def test_mixed_time_is_kept_separate(self):
        s=parse_sources('mtl_sub_update:3:12:0;fb_prepare:1:4096:0')
        self.assertEqual(source_label(s),'mixed+fb_prepare+mtl_sub_update')
        self.assertEqual(classify(source_label(s))['owner'],'unknown')
        self.assertEqual(s['fb_prepare']['bytes'],4096)

    def test_unknown_payload_and_empty_encoders_are_explicit(self):
        self.assertEqual(parse_sources('copy_t2t:2:0:2')['copy_t2t']['unknown_bytes_ops'],2)
        self.assertEqual(source_label({}),'unattributed')
        self.assertEqual(classify('new_unreviewed_path')['owner'],'unknown')

    def test_corrupt_counters_fail_closed(self):
        for value in ('a:0:0:0','a:1:-1:0','a:1:0:2','a:1:0:0;a:1:0:0'):
            with self.assertRaises(ValueError):parse_sources(value)


if __name__=='__main__':unittest.main()
