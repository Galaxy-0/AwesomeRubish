"""Main-camera depth may be elided; independent paint and storage must stay."""
import subprocess
import tempfile
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

class CameraGuardTests(unittest.TestCase):
    def test_protected_gpu_paths(self):
        code=r'''
#include <assert.h>
#include "nvn_spl3_a8.h"
int main(void) {
    nvn_a8_camera_state s={.width=1280,.height=720,.format=0x34,.headless=1,.active=1,.phase=1,.color=1};
    assert(nvn_a8_camera_candidate(s));
    nvn_a8_camera_state p=s;p.width=p.height=1600;p.format=0x36;assert(!nvn_a8_camera_candidate(p));
    p=s;p.depth_write=1;assert(nvn_a8_camera_candidate(p));
    p=s;p.width=p.height=1600;p.format=0x36;p.depth_write=1;assert(!nvn_a8_camera_candidate(p));
    p=s;p.width=p.height=1024;p.format=0x32;p.layers=2;p.color=0;p.depth_write=1;assert(!nvn_a8_camera_candidate(p));
    p.layers=1;assert(!nvn_a8_camera_candidate(p));
    p.layers=2;p.color=1;assert(!nvn_a8_camera_candidate(p));
    p=s;p.stencil_write=1;assert(!nvn_a8_camera_candidate(p));
    p=s;p.storage=1;assert(!nvn_a8_camera_candidate(p));
    p=s;p.capture=1;assert(!nvn_a8_camera_candidate(p));
    p=s;p.color=0;assert(!nvn_a8_camera_candidate(p));
    p=s;p.headless=0;assert(!nvn_a8_camera_candidate(p));
    p=s;p.active=0;assert(!nvn_a8_camera_candidate(p));
    for(int n=0;n<4;n++)if(n!=1){p=s;p.phase=n;assert(!nvn_a8_camera_candidate(p));}
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'guard.c';source.write_text(code);exe=Path(directory)/'guard'
            subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-I'+str(ROOT/'upstream/dm/gfx/nvn'),str(source),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)

    def test_hdr_dependency_aliases_capacity_and_lifetime(self):
        code=r'''
#include <assert.h>
#include "nvn_spl3_a8_taint.h"
int main(void) {
    nvn_a8_taint_set s={0};
    assert(nvn_a8_hdr_target(640,360,0x3f));
    assert(nvn_a8_hdr_target(320,180,0x3f));
    assert(nvn_a8_bloom_shader("03bd7a38cfafd146_b"));
    assert(!nvn_a8_bloom_shader("dd3d1e0ebf732428_b"));
    assert(!nvn_a8_bloom_shader("03bd7a38cfafd146_b_extra"));
    assert(!nvn_a8_hdr_target(1600,1600,0x3f));
    assert(!nvn_a8_hdr_target(640,360,0x36));
    assert(!nvn_a8_hdr_target(640,360,0x34));
    assert(nvn_a8_taint_add(&s,1,100,20));
    assert(nvn_a8_tainted(&s,1,1000,1));
    assert(nvn_a8_tainted(&s,2,119,2));
    assert(nvn_a8_tainted(&s,2,99,2));
    assert(!nvn_a8_tainted(&s,2,120,20));
    assert(!nvn_a8_tainted(&s,2,80,20));
    nvn_a8_taint_forget(&s,1);assert(!nvn_a8_tainted(&s,1,100,20));
    for(unsigned n=0;n<NVN_A8_TAINT_CAP;n++)assert(nvn_a8_taint_add(&s,n+1,1000+100*n,20));
    assert(!nvn_a8_taint_add(&s,9999,100,20));
    nvn_a8_taint_forget(&s,100);assert(nvn_a8_taint_add(&s,9999,100,20));
    assert(nvn_a8_overlap(UINT64_MAX-2,8,UINT64_MAX-1,1));
}'''
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'guard.c';source.write_text(code);exe=Path(directory)/'guard'
            subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-I'+str(ROOT/'upstream/dm/gfx/nvn'),str(source),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)

if __name__=='__main__':unittest.main()
