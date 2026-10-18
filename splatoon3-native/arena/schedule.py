"""Independent room scheduling; void attempts retry the same paired fixture."""
from collections import deque
from concurrent.futures import wait,FIRST_COMPLETED


def schedule(tasks,submit,stop,report,parallel,max_voids,early_rate_check=False,initial_matches=()):
    attempts=list(initial_matches);valid={m['round'] for m in attempts if m.get('passed')}
    if len(valid)!=sum(bool(m.get('passed')) for m in attempts):raise ValueError('duplicate completed fixture')
    pending=deque(dict(t,attempt=t.get('attempt',0)) for t in tasks if t['round'] not in valid)
    running={};reason=None
    def fill():
        while pending and len(running)<parallel and reason is None:
            task=pending.popleft();running[submit(task)]=task
    fill()
    while running:
        ready,_=wait(running,return_when=FIRST_COMPLETED)
        for future in ready:
            task=running.pop(future)
            try:match=future.result()
            except BaseException:
                stop.set();raise
            attempts.append(match)
            if match.get('passed'):
                if task['round'] in valid:raise AssertionError('duplicate valid fixture')
                valid.add(task['round'])
            elif match.get('void') and not match.get('cancelled'):
                pending.appendleft(dict(task,attempt=task['attempt']+1))
            else:
                reason='fatal_match_error';stop.set()
            voids=sum(bool(m.get('void')) for m in attempts)
            if reason is None and voids>max_voids:reason='void_budget_exceeded'
            # A rate-based fallback drains current rooms without cancelling them.
            if reason is None and early_rate_check and len(attempts)>=12 and voids/len(attempts)>.1:
                reason='four_room_void_rate_above_10_percent'
            report(attempts,reason)
        fill()
    return attempts,reason


def overlap_windows(matches,required):
    events=[];windows=[];active={}
    for n,m in enumerate(matches):
        start=m.get('controlled_start_wall');end=m.get('last_progress_wall')
        if start is None or end is None or end<=start:continue
        events.extend([(start,1,n,m),(end,0,n,m)])
    previous=None
    for wall,kind,n,m in sorted(events,key=lambda e:e[:3]):
        if previous is not None and wall>previous and len(active)>=required:
            pids=[p for a in active.values() for p in a['host_pids']]
            if len(set(pids))!=2*len(active):raise AssertionError('room PIDs overlap')
            windows.append(dict(start_wall=previous,end_wall=wall,overlap_seconds=wall-previous,
                                rooms=len(active),hosts=len(pids),host_pids=pids,
                                attempts=[dict(round=a['round'],attempt=a['attempt']) for a in active.values()]))
        if kind:active[n]=m
        else:active.pop(n,None)
        previous=wall
    return windows
