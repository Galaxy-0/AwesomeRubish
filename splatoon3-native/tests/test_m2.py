#!/usr/bin/env python3
"""M2 gate: post-tutorial save copy, DM_KEYS route, reference, 600 s soak."""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from PIL import Image, ImageChops, ImageStat
from test_m1 import ROOT, FRAME, FAILURE

SAVE_SHA256 = "89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd"


def similarity(actual, reference):
    """Local luminance SSIM plus RGB error; animation has limited influence."""
    a, b = [im.convert("RGB").resize((320, 180)) for im in (actual, reference)]
    mae = sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / (3 * 255)
    a, b = a.convert("L"), b.convert("L")
    scores = []
    for y in range(0, 180, 20):
        for x in range(0, 320, 20):
            box = (x, y, x + 20, y + 20)
            av, bv = list(a.crop(box).getdata()), list(b.crop(box).getdata())
            am, bm = sum(av) / 400, sum(bv) / 400
            aa = sum((v - am) ** 2 for v in av) / 400
            bb = sum((v - bm) ** 2 for v in bv) / 400
            ab = sum((v - am) * (w - bm) for v, w in zip(av, bv)) / 400
            scores.append(((2 * am * bm + 6.5025) * (2 * ab + 58.5225)) /
                          ((am * am + bm * bm + 6.5025) * (aa + bb + 58.5225)))
    return {"ssim": sum(scores) / len(scores), "rgb_mae": mae}


def main(args):
    out = ROOT / "work/tests" / datetime.datetime.now().strftime("m2-%Y%m%d-%H%M%S-%f")
    out.mkdir(parents=True)
    errors = []
    result = {"milestone": "M2", "passed": False, "phase": "preflight", "errors": errors}

    def finish():
        (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)
        print(f"M2 artifacts: {out}", flush=True)
        return 1 if errors else 0

    if not args.route.is_file():
        errors.append(f"complete local-lobby route missing: {args.route}")
    if not args.reference.is_file():
        errors.append(f"reviewed local-lobby reference missing: {args.reference}")
    seed = args.save_ref / "save.dat"
    if not seed.is_file():
        errors.append(f"post-tutorial reference save missing: {seed}")
    elif hashlib.sha256(seed.read_bytes()).hexdigest() != SAVE_SHA256:
        errors.append("reference save differs from the designated post-tutorial save")
    else:
        result.update(save_sha256=SAVE_SHA256, save_reference=str(seed.resolve()),
                      save_bytes=seed.stat().st_size)
    if args.frame is None or args.frame < 1:
        errors.append("--frame must identify the verified local-lobby arrival frame")
    if (not math.isfinite(args.soak_seconds) or not math.isfinite(args.arrival_timeout)
            or args.soak_seconds < 600 or args.arrival_timeout <= 0):
        errors.append("M2 requires at least 600 seconds after arrival and a positive arrival timeout")
    if errors:
        return finish()
    route = args.route.read_text().strip()
    if not route or len(route.encode()) >= 4096:
        errors.append("route must be nonempty and fit DM_KEYS' 4096-byte buffer")
    # A diagnostic prefix is intentionally distinct from a complete route.
    if args.route.name == "m2-opening-prefix.keys":
        errors.append("opening prefix is not a complete M2 route")
    starts = []
    for step in route.split(","):
        m = re.fullmatch(r"f(\d+):[^,*]+(?:\*(\d+)/(\d+))?", step)
        if not m:
            errors.append(f"M2 route requires frame-based DM_KEYS steps: {step}")
            break
        frame, count, interval = m.groups()
        starts.append(int(frame) + (int(count or 1) - 1) * int(interval or 0))
    if starts and args.frame < max(starts) + 600:
        errors.append("arrival screenshot must be at least 600 frames after the final input starts")
    with Image.open(args.reference) as ref:
        reference = ref.convert("RGB")
    if reference.size != (1920, 1080) or sum(ImageStat.Stat(reference).var) / 3 < 25:
        errors.append("reference must be a nonblank 1920x1080 local-lobby screenshot")
    if errors:
        return finish()
    result.update(phase="runtime", arrival_frame=args.frame,
                  save_sha256=SAVE_SHA256, save_reference=str(seed.resolve()),
                  ldn_mode="initialized_frontend_only_no_network",
                  route_sha256=hashlib.sha256(route.encode()).hexdigest(),
                  reference_sha256=hashlib.sha256(args.reference.read_bytes()).hexdigest())
    for name in ("save", "temp"):
        (out / name).mkdir()
    shutil.copyfile(seed, out / "save/save.dat")
    if hashlib.sha256((out / "save/save.dat").read_bytes()).hexdigest() != SAVE_SHA256:
        errors.append("run save copy does not match reference")
        return finish()
    # Inherited diagnostics, FIFO inputs or unlock switches must not affect acceptance.
    env = {k: v for k, v in os.environ.items() if not k.startswith("DM_")}
    env.update(DM_ROOT=str(ROOT / "work"), DM_ROMFS=str(ROOT / "work/data/v720896/RomFS"),
               DM_SAVE=str(out / "save"), DM_TEMP=str(out / "temp"),
               DM_MSL_DIR=str(ROOT / "work/build/cache/metal_shader_cache"),
               DM_FONT_DIR=str(ROOT / "work/build/font"), DM_KEYS=route,
               DM_LDN_FRONTEND="1",
               DM_HID_TRACE="1", DM_WATCH_STALL="20",
               DM_WATCH_SAMPLE=str(out / "watchdog.sample.txt"),
               DM_NVN_SHOT=f"{args.frame}:{out}/arrival.png")
    log = out / "host.log"
    samples, arrived = [], None
    start = time.monotonic()
    print(f"M2 artifacts: {out}", flush=True)
    with log.open("wb") as stream:
        proc = subprocess.Popen([str(ROOT / "upstream/dm/host/dmhost"),
                                 str(ROOT / "work/build/patched_v720896")],
                                cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            while True:
                now = time.monotonic()
                if proc.poll() is not None:
                    errors.append(f"host exited before completing soak: {proc.returncode}")
                    break
                text = log.read_text(errors="replace")
                frame = max(map(int, FRAME.findall(text)), default=0)
                samples.append({"seconds": round(now - start, 2), "frame": frame})
                if arrived is None and "arrival.png 成功" in text:
                    arrived = now
                    with Image.open(out / "arrival.png") as actual:
                        metrics = similarity(actual, reference)
                        if actual.size != reference.size:
                            errors.append("arrival screenshot size mismatch")
                    result["similarity"] = metrics
                    if metrics["ssim"] < .90 or metrics["rgb_mae"] > .06:
                        errors.append("arrival screenshot does not match reviewed local-lobby reference")
                        break
                print(f"M2 {now-start:.0f}s frame={frame} soak={0 if arrived is None else now-arrived:.0f}s", flush=True)
                if FAILURE.search(text):
                    errors.append("runtime failure marker in host log")
                    break
                if arrived is None and now - start >= args.arrival_timeout:
                    errors.append("arrival timeout: expected screenshot never completed")
                    break
                if arrived is not None and now - arrived >= args.soak_seconds:
                    break
                time.sleep(5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    errors.append("host failed graceful shutdown within 8 seconds")
    text = log.read_text(errors="replace")
    if proc.returncode or "优雅退出完成" not in text:
        errors.append(f"unclean shutdown: return code {proc.returncode}")
    if FAILURE.search(text):
        errors.append("runtime failure marker in final host log")
    if "LDN Initialize: local frontend initialized; no network" not in text or "LDN SetProtocol: 1" not in text:
        errors.append("local-play frontend did not initialize and configure the NX protocol")
    if hashlib.sha256(seed.read_bytes()).hexdigest() != SAVE_SHA256:
        errors.append("reference save changed during the run")
    if len(samples) < 3 or samples[-1]["frame"] <= samples[-3]["frame"]:
        errors.append("frame count stalled in the final sampling window")
    soak = 0 if arrived is None else time.monotonic() - arrived
    if soak < args.soak_seconds:
        errors.append("did not complete the required post-arrival soak")
    result.update(passed=not errors, samples=samples, soak_seconds=soak, returncode=proc.returncode)
    return finish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", type=Path, default=ROOT / "tools/routes/m2-local-lobby.keys")
    parser.add_argument("--reference", type=Path, default=ROOT / "work/m2/reference-local-lobby.png")
    parser.add_argument("--save-ref", type=Path, default=ROOT / "work/save_ref")
    parser.add_argument("--frame", type=int, default=2400,
                        help="verified Private Battle menu screenshot frame (default: 2400)")
    parser.add_argument("--arrival-timeout", type=float, default=1200)
    parser.add_argument("--soak-seconds", type=float, default=600)
    raise SystemExit(main(parser.parse_args()))
