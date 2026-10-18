"""Common monotonic game clock; policy waiting is removed once for every peer."""
import ctypes
import mmap
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


class SharedClock:
    def __init__(self,path):
        self.path=Path(path)
        source=ROOT/'tools/rl_clock.c';header=ROOT/'upstream/dm/host/dm_rl_clock.h'
        library=ROOT/'work/build/rl_clock.dylib' if sys.platform=='darwin' else ROOT/'work/build/rl_clock.so'
        if not library.exists() or library.stat().st_mtime<max(source.stat().st_mtime,header.stat().st_mtime):
            library.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run([os.environ.get('CC','cc'),'-std=c11','-O2','-Wall','-Wextra','-Werror',
                            *(['-dynamiclib'] if sys.platform=='darwin' else ['-shared','-fPIC','-D_POSIX_C_SOURCE=200809L']),
                            str(source),'-o',str(library)],check=True)
        self.lib=ctypes.CDLL(str(library))
        for name in ('init','read','pause','resume'):
            fn=getattr(self.lib,'rl_clock_'+name);fn.argtypes=[ctypes.c_void_p]
            fn.restype=ctypes.c_int if name=='init' else None if name=='resume' else ctypes.c_uint64
        fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
        try:
            os.ftruncate(fd,24);self.mapping=mmap.mmap(fd,24)
        finally:os.close(fd)
        self.buffer=(ctypes.c_char*24).from_buffer(self.mapping)
        self.pointer=ctypes.addressof(self.buffer)
        if not self.lib.rl_clock_init(self.pointer):raise RuntimeError('64-bit shared atomics must be lock free')

    def read(self):return self.lib.rl_clock_read(self.pointer)
    def pause(self):return self.lib.rl_clock_pause(self.pointer)
    def resume(self):self.lib.rl_clock_resume(self.pointer)
    def close(self):
        self.resume();del self.buffer;self.mapping.close()
