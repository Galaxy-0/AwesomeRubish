"""Script-only performance diagnosis: hold input across a native RPC chunk.

Not human recording: identifies barrier overhead before changing control transport.
No interpolation or BC export is allowed from this diagnostic.
"""

import argparse, json, time
from functools import partial
from pathlib import Path
from rl import NativeParallelEnv
from rl.native_start import validate_runtime
from rl.demo.capture import DemoSession, as_native, scripted, safe_out, write


def main(a):
    h, m = validate_runtime(a.host, a.modules, allow_demo=True)
    out = safe_out(a.out)
    out.mkdir(parents=True, exist_ok=False)
    env = NativeParallelEnv(
        players=2,
        weapons=[8000, 50],
        stage_id=1,
        mode=0,
        frame_skip=a.chunk,
        pixels=False,
        reward_fn=None,
        timeout=1200,
        patched=m,
        session_factory=partial(DemoSession, host=h, demo_present_link=a.present_link),
    )
    result = dict(
        kind="script-only RPC chunk diagnostic, NOT demonstration corpus",
        chunk=a.chunk,
        errors=[],
    )
    try:
        _, origin = env.reset()
        result["session"] = str(env.session.out)
        result["origins"] = origin
        times = []
        start = time.monotonic()
        for frame in range(0, a.frames, a.chunk):
            action = scripted(frame)
            other = scripted(frame)
            other["sticks"] = [0, 0, 0, 0]
            t = time.monotonic_ns()
            _, _, _, _, info = env.step(
                {"player_0": as_native(action), "player_1": as_native(other)}
            )
            times.append(
                dict(
                    start_frame=frame,
                    end_frame=frame + a.chunk,
                    send_ns=t,
                    ack_ns=time.monotonic_ns(),
                )
            )
            if frame % 600 == 0:
                print(
                    json.dumps(dict(frame=frame, seconds=time.monotonic() - start)),
                    flush=True,
                )
        result.update(
            frames=a.frames,
            seconds=time.monotonic() - start,
            presents_per_second=a.frames / (time.monotonic() - start),
            timing=times,
            passed=True,
        )
    except BaseException as e:
        result.update(passed=False, errors=[repr(e)])
    finally:
        env.close()
        write(out / "result.json", result)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ["origins", "timing"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", type=Path, required=True)
    p.add_argument("--modules", type=Path, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--chunk", type=int, default=8)
    p.add_argument("--frames", type=int, default=1800)
    p.add_argument("--present-link", type=int, default=1)
    main(p.parse_args())
