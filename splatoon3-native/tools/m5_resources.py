#!/usr/bin/env python3
"""Local M5 sampling and bounded memory admission. No privileged commands."""
import json
from pathlib import Path
import re
import subprocess
import time


def command(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL, timeout=45)


def system_sample():
    swap = command(['sysctl', '-n', 'vm.swapusage'])
    vm = command(['vm_stat'])
    pagesize = int(re.search(r'page size of (\d+)', vm)[1])
    pages = {k: int(v) for k, v in re.findall(r'^([^:\n]+):\s+(\d+)\.', vm, re.M)}
    gpu = command(['ioreg', '-r', '-c', 'AGXAccelerator', '-d', '1'])
    stats = {k: int(v) for k, v in re.findall(r'"([^"\n]+)"=(\d+)', gpu)}
    return dict(time=time.time(), swap_mib=float(re.search(r'used = ([\d.]+)M', swap)[1]),
                pressure=int(command(['sysctl', '-n', 'kern.memorystatus_vm_pressure_level']).strip()),
                compressor_mib=pages.get('Pages occupied by compressor', 0)*pagesize/2**20,
                page_size=pagesize, pageouts=pages.get('Pageouts', 0), swapouts=pages.get('Swapouts', 0),
                free_mib=pages.get('Pages free', 0)*pagesize/2**20,
                gpu={k: stats[k] for k in ('Device Utilization %', 'Renderer Utilization %',
                     'Tiler Utilization %', 'In use system memory', 'Alloc system memory') if k in stats})


def memory_row(path):
    if not path.exists(): return {}
    lines = path.read_text().splitlines()
    if len(lines) < 3: return {}
    keys = lines[1].split('\t'); vals = lines[-1].split('\t')
    row = dict(zip(keys, vals))
    return {k: float(v) if '/' not in v else [int(x) for x in v.split('/')]
            for k, v in row.items()}


class Monitor:
    def __init__(self, out):
        self.out = Path(out); self.baseline = system_sample(); self.rows = []
        (self.out/'system-baseline.json').write_text(json.dumps(self.baseline, indent=2)+'\n')

    def sample(self, hosts):
        row = system_sample(); row['hosts'] = []
        for player, p, d in hosts:
            text = (d/'host.log').read_text(errors='replace')
            frames = re.findall(r'RESOURCE_FRAME frame=(\d+) seconds=([\d.]+)', text)
            legacy = re.findall(r'\[nvn\] 帧 (\d+)：', text)
            row['hosts'].append(dict(player=player, pid=p.pid,
                frame=int(frames[-1][0]) if frames else max(map(int,legacy), default=0),
                clock=float(frames[-1][1]) if frames else None,
                phase='results' if 'PROBE main+0x3dd9370' in text else ('judging' if 'PROBE main+0x3dcc710' in text else ('in_game' if 'PROBE main+0x3db55d0' in text else ('loading' if (d.parent/'load-slots/active').exists() else ('lobby' if legacy and int(legacy[-1])>=4200 else 'boot')))),
                memory=memory_row(d/'memory.tsv')))
        row['rss_sum_mib'] = sum(h['memory'].get('rss', 0) for h in row['hosts'])
        row['footprint_sum_mib'] = sum(h['memory'].get('phys_footprint', 0) for h in row['hosts'])
        row['new_swapout_bytes'] = max(0, row['swapouts']-self.baseline['swapouts'])*row['page_size']
        self.rows.append(row)
        with (self.out/'resources.jsonl').open('a') as f: f.write(json.dumps(row)+'\n')
        # Warning is allowed. Count actual newly swapped-out bytes, not changes
        # in swap usage (which may shrink while other pages are swapped out).
        if row['new_swapout_bytes'] > 2*2**30:
            raise RuntimeError('resource stop: additional swapout exceeds 2 GiB')
        if row['pressure'] >= 4:
            raise RuntimeError('resource stop: critical memory pressure')
        return row

    def snapshot(self, hosts, label):
        pids = [str(p.pid) for _, p, _ in hosts]
        for player, p, d in hosts:
            (d/f'{label}-vmmap.txt').write_text(command(['vmmap', '-summary', str(p.pid)]))
        (self.out/f'{label}-footprint.txt').write_text(command(['footprint', '--wide', '--swapped', *pids]))
        shared=[]; union=set(); occurrences=0; page_size=16384
        requests=[]
        for _,p,d in hosts:
            output=d/'memory.tsv.shared.tsv'
            old=output.stat().st_mtime_ns if output.exists() else 0
            (d/'memory.tsv.request').touch()
            requests.append((d,output,old))
        deadline=time.monotonic()+15
        for d,output,old in requests:
            while not output.exists() or output.stat().st_mtime_ns<=old:
                if time.monotonic()>deadline:raise RuntimeError('shared-page snapshot timed out')
                time.sleep(.1)
            data=output.read_text();(d/f'{label}-shared.tsv').write_text(data)
            keys=set()
            for line in data.splitlines():
                if line.startswith('#'):continue
                dev,ino,offset,refs,path=line.split('\t',4)
                keys.add((dev,ino,offset))
            occurrences+=len(keys);union.update(keys)
            shared.append(dict(player=d.name,clean_file_pages=len(keys)))
        (self.out/f'{label}-shared.json').write_text(json.dumps(dict(
            page_size=page_size,hosts=shared,mapped_clean_mib=occurrences*page_size/2**20,
            unique_clean_mib=len(union)*page_size/2**20,
            duplicate_clean_mib=(occurrences-len(union))*page_size/2**20,
            scope='Resident clean external project file pages only; excludes COW, dirty, GPU and guest pages.'),indent=2)+'\n')

    def summary(self):
        rows = self.rows
        return dict(samples=len(rows), baseline=self.baseline,
            max_rss_sum_mib=max((r['rss_sum_mib'] for r in rows), default=0),
            max_footprint_sum_mib=max((r['footprint_sum_mib'] for r in rows), default=0),
            swap_growth_mib=max((r['swap_mib']-self.baseline['swap_mib'] for r in rows), default=0),
            max_new_swapout_bytes=max((r['new_swapout_bytes'] for r in rows), default=0),
            max_pressure=max((r['pressure'] for r in rows), default=1),
            max_compressor_mib=max((r['compressor_mib'] for r in rows), default=0),
            gpu_util_percent=[r['gpu'].get('Device Utilization %') for r in rows],
            note='RSS sums include shared pages; see group footprint snapshots for deduplication. Metal allocated size overlaps guest no-copy pools; do not add it to RSS.')
