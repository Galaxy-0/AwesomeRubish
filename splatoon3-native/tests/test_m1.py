#!/usr/bin/env python3
"""M1 integration gate. Requires the locally extracted game and built host."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
FRAME = re.compile(r"\[nvn\] 帧 (\d+)：")
FAILURE = re.compile(r"CRASH|FATAL|invalid source|看门狗：|命令缓冲执行出错|命令缓冲错误详情")


def run(seconds, save_ref=None):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    out = ROOT / "work/tests" / f"m1-{stamp}"
    out.mkdir(parents=True)
    for name in ("save", "temp"):
        (out / name).mkdir()
    save_sha256 = None
    if save_ref is not None:
        seed = save_ref / "save.dat"
        save_sha256 = hashlib.sha256(seed.read_bytes()).hexdigest()
        shutil.copyfile(seed, out / "save/save.dat")
    env = {k: v for k, v in os.environ.items() if not k.startswith("DM_")}
    env.update(
        DM_ROOT=str(ROOT / "work"),
        DM_ROMFS=str(ROOT / "work/data/v720896/RomFS"),
        DM_SAVE=str(out / "save"),
        DM_TEMP=str(out / "temp"),
        DM_MSL_DIR=str(ROOT / "work/build/cache/metal_shader_cache"),
        DM_FONT_DIR=str(ROOT / "work/build/font"),
        DM_KEYS="",
        DM_WATCH_STALL="15",
        DM_WATCH_SAMPLE=str(out / "watchdog.sample.txt"),
        DM_NVN_SHOT=f"600,1200,2400:{out}/frame_%d.png",
    )
    log = out / "host.log"
    errors, samples, images = [], [], []
    print(f"M1 artifacts: {out}", flush=True)
    start = time.monotonic()
    with log.open("wb") as stream:
        proc = subprocess.Popen(
            [str(ROOT / "upstream/dm/host/dmhost"), str(ROOT / "work/build/patched_v720896")],
            cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
        )
        try:
            while time.monotonic() - start < seconds:
                if proc.poll() is not None:
                    errors.append(f"host exited before test duration: {proc.returncode}")
                    break
                elapsed = time.monotonic() - start
                frames = [int(f) for f in FRAME.findall(log.read_text(errors="replace"))]
                frame = max(frames, default=0)
                samples.append({"seconds": round(elapsed, 2), "frame": frame})
                print(f"M1 {elapsed:.0f}s frame={frame}", flush=True)
                time.sleep(min(5, max(0, seconds - elapsed)))
        finally:
            if proc.poll() is None:
                proc.terminate()  # dmhost's SIGTERM lifecycle drains graphics and exits 0.
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    errors.append("host did not terminate within 8 seconds")
    text = log.read_text(errors="replace")
    frames = [int(f) for f in FRAME.findall(text)]
    final_frame = max(frames, default=0)
    if proc.returncode != 0:
        errors.append(f"host return code {proc.returncode}")
    if final_frame < 2400:
        errors.append(f"did not reach frame 2400: {final_frame}")
    if len(samples) < 3 or samples[-1]["frame"] <= samples[-3]["frame"]:
        errors.append("frame count did not increase during the final sample window")
    failures = FAILURE.findall(text)
    if failures:
        errors.append(f"runtime failure markers: {sorted(set(failures))}")
    if "优雅退出完成" not in text:
        errors.append("graceful shutdown was not completed")
    if save_ref is not None and hashlib.sha256(seed.read_bytes()).hexdigest() != save_sha256:
        errors.append("reference save changed during the run")
    for frame in (600, 1200, 2400):
        path = out / f"frame_{frame}.png"
        if not path.exists():
            errors.append(f"missing screenshot at frame {frame}")
            continue
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            stat = ImageStat.Stat(rgb)
            variance = sum(stat.var) / 3
            nonblack = 1 - rgb.convert("L").histogram()[0] / (rgb.width * rgb.height)
            images.append({"frame": frame, "size": list(rgb.size), "variance": variance, "nonblack_fraction": nonblack})
            if rgb.size != (1920, 1080) or variance < 25 or nonblack < 0.05:
                errors.append(f"frame {frame} failed 1080p/nonblack gate")
    result = {"passed": not errors, "seconds": seconds, "final_frame": final_frame,
              "save_reference": str(save_ref) if save_ref is not None else None,
              "save_sha256": save_sha256,
              "returncode": proc.returncode, "samples": samples, "images": images, "errors": errors}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2), flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=75)
    parser.add_argument("--save-ref", type=Path, help="copy this directory's save.dat into a fresh run")
    args = parser.parse_args()
    if args.seconds < 45:
        parser.error("M1 requires at least 45 seconds")
    if args.save_ref is not None and not (args.save_ref / "save.dat").is_file():
        parser.error("--save-ref must contain save.dat")
    raise SystemExit(run(args.seconds, args.save_ref))
