"""CPU contract checks of the exact private native predicate helper."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class PredicateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        folder = Path(cls.tmp.name)
        cls.program = folder / "check"
        source = folder / "check.c"
        header = Path(__file__).with_name("render_predicate.inc").resolve()
        source.write_text(
            r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <assert.h>
#define MLOG(...) do{}while(0)
#define MDIE(...) do{fprintf(stderr,__VA_ARGS__);abort();}while(0)
"""
            + f'#include "{header}"\n'
            + r"""
static int active=1,phase=1;
int dm_rl_active(void){return active;}
int dm_rl_match_phase(void){return phase;}
uint64_t dm_nvn_frame_count(void){return 601;}
void dm_gfx_shot_at(long a,const char *b){(void)a;(void)b;}
int main(int argc,char **argv){
 assert(argc==2);if(strcmp(argv[1],"default"))setenv("DM_DEMO_PREDICATE",argv[1],1);
 uint64_t data[4]={0,11,0,22},original[4];memcpy(original,data,sizeof data);
 uint64_t addr=(uint64_t)(uintptr_t)data;int enabled=0;
 if(!strcmp(argv[1],"strict") || !strcmp(argv[1],"default")){assert(!demo_predicate(1,addr,1,&enabled));return 0;}
 assert(demo_predicate(1,addr,1,&enabled));assert(enabled==1);
 assert(!memcmp(original,data,sizeof data));
 if(!strcmp(argv[1],"always")){assert(demo_pred_n==0);assert(!demo_predicate(0,addr,0,&enabled));phase=2;assert(!demo_predicate(1,addr,0,&enabled));return 0;}
 assert(demo_pred_n==1);unsigned n;uint64_t *p=demo_pred_take(&n);
 demo_pred_publish(p,n,10);assert(demo_predicate(1,addr,1,&enabled));assert(!enabled);
 data[0]=14; // A later result exists in RAM but is not published to the cache.
 assert(demo_predicate(1,addr,0,&enabled));assert(enabled);
 p=demo_pred_take(&n);demo_pred_publish(p,n,11);
 assert(demo_predicate(1,addr,0,&enabled));assert(!enabled);
 data[0]=0;p=demo_pred_take(&n);demo_pred_publish(p,n,9); // Older completion cannot overwrite.
 assert(demo_predicate(1,addr,0,&enabled));assert(!enabled);
 assert(data[1]==11 && data[3]==22); // Timestamps are never operands or overwritten.
 assert(!demo_predicate(0,addr,0,&enabled)); // Direct disable stays native.
 phase=2;assert(!demo_predicate(1,addr,0,&enabled));
 phase=1;active=0;assert(!demo_predicate(1,addr,0,&enabled));
 return 0;
}
"""
        )
        subprocess.run(
            ["clang", "-O1", str(source), "-o", str(cls.program), "-pthread"],
            check=True,
            capture_output=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check(self, mode, fixture=True):
        env = {k: v for k, v in os.environ.items() if not k.startswith("DM_")}
        if fixture:
            env["DM_TEST_DEMO"] = "1"
        return subprocess.run([str(self.program), mode], env=env, capture_output=True)

    def test_default_strict(self):
        self.assertEqual(self.check("strict", False).returncode, 0)
        self.assertEqual(self.check("default", False).returncode, 0)

    def test_async_completed_cache_no_writes(self):
        self.assertEqual(self.check("async").returncode, 0)

    def test_unconditional_keeps_direct_controls(self):
        self.assertEqual(self.check("always").returncode, 0)

    def test_fixture_flag_required(self):
        result = self.check("async", False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"requires isolated", result.stderr)


if __name__ == "__main__":
    unittest.main()
