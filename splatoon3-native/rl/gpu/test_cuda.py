"""Independent CUDA/Torch and complete CUDA-graph state-advance checks."""

import argparse, json
from pathlib import Path
import torch
from .env import ParallelEnv, SQUID, SUB, GROUND, PHASE, PREV_ZR, PREV_RS
from .test_env import fixture_config
from .cuda_graph import GraphEnv


def main(a):
    torch.set_num_threads(1)
    torch.manual_seed(314159)
    # Same deterministic source and shape; batch16 covers distinct RNG counters.
    config = fixture_config(decision_frames=2)
    atol = 1e-5 if a.compile else 1e-6
    maxima = {}

    def compare(left, right, name):
        if left.dtype.is_floating_point:
            maxima[name] = max(
                maxima.get(name, 0.0),
                float((left - right).abs().max().item()) if left.numel() else 0.0,
            )
        torch.testing.assert_close(
            left, right, rtol=0, atol=atol if left.dtype.is_floating_point else 0
        )

    def semantics(left, right, lobs, robs):
        for slot in [SQUID, SUB, GROUND, PHASE, *range(PREV_ZR, PREV_RS + 1)]:
            torch.testing.assert_close(
                left[..., slot], right[..., slot], rtol=0, atol=0
            )
        torch.testing.assert_close(
            lobs["screen"][..., 1:], robs["screen"][..., 1:], rtol=0, atol=0
        )
        torch.testing.assert_close(
            lobs["entities"][..., 3], robs["entities"][..., 3], rtol=0, atol=0
        )

    reference = ParallelEnv(a.data, config, n_envs=16, device="cuda")
    faster = ParallelEnv(
        a.data, config, n_envs=16, device="cuda", fast_rays=True, compile=a.compile
    )
    reference.reset(seed=123)
    faster.reset(seed=123)
    # Rays include exact voxel centres/half-integers and boundary/outside cases.
    origins = (
        torch.rand((8192, 3), device="cuda")
        * torch.tensor([150.0, 60.0, 260.0], device="cuda")
        + reference.geo.origin
    )
    directions = torch.randn((8192, 3), device="cuda")
    directions /= directions.norm(dim=-1, keepdim=True)
    x = reference.geo.ray(origins, directions, 64.0, 1.0)
    y = faster.geo.ray(origins, directions, 64.0, 1.0)
    for left, right in zip(x, y):
        torch.testing.assert_close(left, right, rtol=0, atol=0)
    print(json.dumps(dict(event="rays-passed", rays=8192)), flush=True)
    for step in range(20):
        actions = reference.random_actions()
        left = reference.step(actions)
        right = faster.step(actions)
        compare(reference.state, faster.state, "state")
        semantics(reference.state, faster.state, left[0], right[0])
        for key in left[0]:
            compare(left[0][key], right[0][key], "obs_" + key)
        compare(left[1], right[1], "rewards")
    print(json.dumps(dict(event="eager-fast-rays-passed", decisions=20)), flush=True)
    # Verify a persistent capture advances changing actions and frame counters,
    # including partial reset. Compare every state/shot/paint and public output.
    captured = GraphEnv(faster)
    reference.reset(seed=7)
    captured.reset(seed=7)
    for step in range(20):
        actions = reference.random_actions()
        left = reference.step(actions)
        right = captured.step(actions)
        for name in ["state", "shots", "paint", "steps", "dead"]:
            compare(getattr(reference, name), getattr(captured, name), name)
        semantics(reference.state, captured.state, left[0], right[0])
        for key in left[0]:
            compare(left[0][key], right[0][key], "obs_" + key)
        compare(left[1], right[1], "rewards")
        if step == 11:
            mask = torch.arange(16, device="cuda") % 2 == 0
            reference.reset(seed=19, options={"mask": mask})
            captured.reset(seed=19, options={"mask": mask})
    result = dict(
        passed=True,
        device=torch.cuda.get_device_name(),
        torch=torch.__version__,
        ray_checks=8192,
        graph_checked_decisions=20,
        partial_reset_checked=True,
        config_is_synthetic=True,
        compiled=a.compile,
        floating_atol=atol,
        maxima=maxima,
        discrete_semantics_exact=True,
    )
    Path(a.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--compile", action="store_true")
    main(p.parse_args())
