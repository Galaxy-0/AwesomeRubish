"""Owned offline smoke/throughput runner; deliberately no training algorithm."""

import argparse, json, time, math
from dataclasses import asdict
from pathlib import Path
import torch
from .contract import Config
from .env import ParallelEnv
from .record import Recorder


def main(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    # Provisional values are visible in every output; never certify calibration.
    conf = (
        json.loads(Path(a.calibration).read_text())
        if a.calibration
        else dict(
            stick_plus5_radians_per_frame=0.04,
            camera_horizontal_fov_degrees=90,
            camera_vertical_fov_degrees=60,
            camera_distance=6.0,
            camera_target_height=2.2,
            camera_pitch_offset_radians=0.0,
        )
    )
    calibrated = bool(a.calibration) and bool(conf.get("accepted", False))
    conf = conf.get("config", conf)
    config = Config(**conf, decision_frames=a.decision_frames, duration_frames=10800)
    torch.set_num_threads(a.cpu_threads)
    torch.manual_seed(a.seed)
    start = time.perf_counter()
    e = ParallelEnv(
        a.data,
        config,
        n_envs=a.n_envs,
        device=a.device,
        compile=a.compile,
        fast_rays=a.fast_rays,
    )

    if a.cuda_graph:
        from .cuda_graph import GraphEnv

        e = GraphEnv(e)

    def sync():
        if e.device.type == "cuda":
            torch.cuda.synchronize()

    bank = torch.stack([e.random_actions() for _ in range(64)])
    actions = bank[0]
    sync()
    construction = time.perf_counter() - start
    if a.mode == "benchmark":
        print(
            json.dumps(
                dict(
                    event="warmup",
                    n_envs=e.n,
                    compile=a.compile,
                    construction=construction,
                )
            ),
            flush=True,
        )
        for i in range(a.warmup):
            e.step(bank[(i // 16) % 64])
            if i in [0, 1, 3, 9]:
                sync()
                print(json.dumps(dict(event="warmup-step", i=i)), flush=True)
        e.reset(seed=a.seed)
        sync()
        start = time.perf_counter()
        # Real full partial observation tensors on every step, never observe=False.
        for i in range(a.steps):
            obs, reward, term, trunc, info = e.step(bank[(i // 16) % 64])
        sync()
        wall = time.perf_counter() - start
        result = dict(
            schema="inklab.rl.stage0.benchmark.v1",
            n_envs=e.n,
            agents=2,
            decision_frames=a.decision_frames,
            steps=a.steps,
            environment_frames=e.n * a.steps * a.decision_frames,
            wall_seconds=wall,
            environment_frames_per_second=e.n * a.steps * a.decision_frames / wall,
            including_observations=True,
            including_reset=False,
            including_rng=False,
            action_source="64 pre-generated GPU random actions, held16 decisions per group",
            compile=a.compile,
            fast_rays=a.fast_rays,
            cuda_graph=a.cuda_graph,
            torch=torch.__version__,
            device=str(e.device),
            gpu=torch.cuda.get_device_name() if e.device.type == "cuda" else None,
            peak_allocated_mib=torch.cuda.max_memory_allocated() / 2**20
            if e.device.type == "cuda"
            else None,
            peak_reserved_mib=torch.cuda.max_memory_reserved() / 2**20
            if e.device.type == "cuda"
            else None,
            config=asdict(config),
            native_calibrated=calibrated,
            seed=a.seed,
        )
        result["throughput_threshold_passed"] = (
            result["environment_frames_per_second"] >= 200000
        )
        # Throughput alone is not milestone acceptance.
    else:
        record = Recorder(e, stride=6) if a.trace else None
        finite = True
        zero_sum = True
        start = time.perf_counter()
        e.reset(seed=a.seed)
        maxima = dict(damage=0.0, deaths=0.0, shots=0.0, hooks=0.0, returns=0.0)
        for i in range(math.ceil(config.duration_frames / config.decision_frames)):
            # Preserve short held sequences so random actions include valid charges.
            if i % 16 == 0:
                actions = e.random_actions()
            obs, reward, term, trunc, info = e.step(actions)
            finite &= bool(torch.isfinite(e.state).all().item()) and all(
                bool(torch.isfinite(v).all().item())
                for v in obs.values()
                if v.dtype.is_floating_point
            )
            zero_sum &= bool((reward.sum(-1).abs() < 1e-6).all().item())
            if record:
                record.capture(actions, info)
            if i % 300 == 0:
                print(
                    json.dumps(
                        dict(
                            event="random-progress",
                            step=i,
                            frame=int(e.steps[0].item()),
                        )
                    ),
                    flush=True,
                )
            total = info["events"].sum((0, 1)).detach().cpu().tolist()
            for key, v in zip(maxima, total):
                maxima[key] += v
        sync()
        wall = time.perf_counter() - start
        result = dict(
            schema="inklab.rl.stage0.random.v1",
            n_envs=e.n,
            frames=e.steps.detach().cpu().tolist(),
            finite=finite,
            zero_sum=zero_sum,
            all_terminated=bool(term.all().item()),
            truncated=bool(trunc.any().item()),
            wall_seconds=wall,
            events=maxima,
            config=asdict(config),
            native_calibrated=calibrated,
            seed=a.seed,
        )
        result["passed"] = (
            finite and zero_sum and result["all_terminated"] and not result["truncated"]
        )
        if record:
            record.write(out / "trace.json")
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--calibration")
    p.add_argument("--device", default="cuda")
    p.add_argument("--n-envs", type=int, default=128)
    p.add_argument("--cpu-threads", type=int, default=1)
    p.add_argument("--decision-frames", type=int, default=2)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--compile", action="store_true")
    p.add_argument("--cuda-graph", action="store_true")
    p.add_argument("--fast-rays", action="store_true")
    p.add_argument("--trace", action="store_true")
    p.add_argument("--mode", choices=["benchmark", "random"], default="benchmark")
    p.add_argument("--steps", type=int, default=50)
    p.add_argument("--warmup", type=int, default=10)
    main(p.parse_args())
