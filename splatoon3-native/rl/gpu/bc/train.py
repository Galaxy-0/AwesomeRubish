"""Small recurrent BC baseline: whole-match holdout, no game/RL reward updates."""

import argparse
import json
import time
from pathlib import Path
import torch
from torch.nn import functional as F
from .model import BCPolicy
from .data import HEADS, load_match, sequence_starts, metric


def obs_only(data):
    return {k: v for k, v in data.items() if k not in ("labels", "frame")}


@torch.no_grad()
def score(model, matches, device):
    logits, labels = [], []
    model.eval()
    for data in matches:
        hidden = model.initial(1, device)
        prior = None
        for start in range(0, len(data["frame"]), 128):
            end = min(len(data["frame"]), start + 128)
            # Gaps reset memory rather than leaking a discontinuous history.
            frames = data["frame"][start:end]
            done = torch.zeros((end - start, 1), device=device, dtype=torch.bool)
            done[0] = prior is None or int(frames[0]) - prior != 2
            if len(frames) > 1:
                done[1:, 0] = (frames[1:] - frames[:-1] != 2).to(device)
            obs = {k: v[start:end, None].to(device) for k, v in obs_only(data).items()}
            out, _, hidden = model(obs, hidden, done)
            logits.append(out[:, 0].cpu())
            labels.append(data["labels"][start:end])
            prior = int(frames[-1])
    return torch.cat(logits), torch.cat(labels)


def baselines(train, val):
    """Fit priors on training matches ONLY, Jeffreys smoothing for finite CE."""
    result = {}
    for h, name in enumerate(HEADS):
        count = torch.bincount(train[:, h], minlength=17).double()
        size = (17, 9, 9, 3, 3, 2, 1, 1)[h]
        probabilities = (count[:size] + 0.5) / (count[:size].sum() + 0.5 * size)
        top = int(count.argmax())
        result[name] = dict(majority_class=top)
        for split, y in (("train", train), ("val", val)):
            result[name][split] = dict(
                accuracy=float((y[:, h] == top).float().mean()),
                cross_entropy=float(-probabilities[y[:, h]].log().mean()),
            )
    return result


def persistence_baseline(train, train_previous, val, val_previous):
    """Causal one-step Markov baseline; detects action-feedback copy shortcuts."""
    result = {}
    for h, name in enumerate(HEADS):
        size = (17, 9, 9, 3, 3, 2, 1, 1)[h]
        count = torch.zeros(17, size, dtype=torch.float64)
        count.index_put_(
            (train_previous[:, h], train[:, h]),
            torch.ones(len(train), dtype=torch.float64),
            accumulate=True,
        )
        probability = (count + 0.5) / (count.sum(-1, keepdim=True) + size * 0.5)
        result[name] = {}
        for split, y, previous in (
            ("train", train, train_previous),
            ("val", val, val_previous),
        ):
            p = probability[previous[:, h]]
            result[name][split] = dict(
                accuracy=float((p.argmax(-1) == y[:, h]).float().mean()),
                cross_entropy=float(-p.gather(-1, y[:, h, None]).log().mean()),
            )
    return result


def edge_weights(labels, enabled=False):
    weights = torch.ones(8, 17)
    if enabled:
        for h in (3, 4):
            count = torch.bincount(labels[:, h], minlength=17).float()
            weights[h, :3] = (count.max() / count[:3].clamp_min(1)).sqrt().clamp_max(8)
    return weights


def cloning_loss(logits, labels, weights):
    # Equal weight per head; R/RS are disabled, not training targets.
    return torch.stack(
        [
            F.cross_entropy(
                logits[..., h, :].reshape(-1, 17),
                labels[..., h].reshape(-1),
                weight=weights[h],
            )
            for h in range(6)
        ]
    ).mean()


def main(a):
    torch.set_num_threads(2)
    torch.set_float32_matmul_precision("high")
    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    if set(map(lambda p: str(Path(p).resolve()), a.train)) & {
        str(Path(a.val).resolve())
    }:
        raise ValueError("whole-match train/val overlap")
    train, reports = [], {}
    for path in [*a.train, a.val]:
        data, report = load_match(path)
        reports[str(path)] = report
        if path == a.val:
            val = data
        else:
            train.append(data)
    baseline = baselines(torch.cat([d["labels"] for d in train]), val["labels"])
    (out / "dataset.json").write_text(
        json.dumps(dict(matches=reports, baseline=baseline, config=vars(a)), indent=2)
        + "\n"
    )
    print(
        json.dumps(
            dict(
                event="loaded",
                samples=[len(d["frame"]) for d in train],
                val=len(val["frame"]),
            )
        ),
        flush=True,
    )
    model = BCPolicy(a.hidden).to(a.device)
    weights = edge_weights(torch.cat([d["labels"] for d in train]), a.edge_balance).to(
        a.device
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    chunks = [
        (i, s) for i, d in enumerate(train) for s in sequence_starts(d, a.length, 2)
    ]
    # Keep packed CPU data: ~400MB, not a second persistent copy on the GPU.
    best, stale = float("inf"), 0
    start = time.perf_counter()
    curves = []
    for epoch in range(1, a.epochs + 1):
        model.train()
        order = torch.randperm(len(chunks)).tolist()
        loss_sum, steps = 0.0, 0
        for at in range(0, len(order), a.batch):
            picked = [chunks[i] for i in order[at : at + a.batch]]
            batch = {
                k: torch.stack(
                    [train[i][k][s : s + a.length] for i, s in picked], 1
                ).to(a.device)
                for k in train[0]
            }
            logits, _, _ = model(obs_only(batch), model.initial(len(picked), a.device))
            # R/RS are permanently disabled and have no learning signal.
            loss = cloning_loss(logits, batch["labels"], weights)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            loss_sum += float(loss.detach())
            steps += 1
        vl, vy = score(model, [val], a.device)
        stats = metric(vl, vy)
        selection = float(cloning_loss(vl, vy, weights.cpu()))
        row = dict(
            epoch=epoch,
            train_batch_loss=loss_sum / max(1, steps),
            val=stats,
            selection_ce=selection,
            seconds=time.perf_counter() - start,
        )
        curves.append(row)
        with (out / "curves.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)
        if selection < best - 1e-4:
            best, stale = selection, 0
            torch.save(
                dict(
                    schema="inklab.rl.bc.checkpoint.v1",
                    policy=model.state_dict(),
                    hidden_size=a.hidden,
                    epoch=epoch,
                    config=vars(a),
                ),
                out / "best.pt",
            )
        else:
            stale += 1
        if stale >= a.patience:
            break
    state = torch.load(out / "best.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(state["policy"])
    result = dict(
        schema="inklab.rl.bc.fit.v1",
        parameters=sum(p.numel() for p in model.parameters()),
        best_epoch=state["epoch"],
        epochs=epoch,
        seconds=time.perf_counter() - start,
        peak_cuda_mib=torch.cuda.max_memory_allocated() / 2**20
        if a.device.startswith("cuda")
        else 0,
        baseline=baseline,
        edge_loss_weights=weights.cpu().tolist(),
        splits={},
    )
    for name, matches in (("train", train), ("val", [val])):
        logits, y = score(model, matches, a.device)
        metrics = metric(logits, y)
        for h, head in enumerate(HEADS):
            minority = y[:, h] != baseline[head]["majority_class"]
            metrics[head]["nonmajority_accuracy"] = (
                float((logits[minority, h].argmax(-1) == y[minority, h]).float().mean())
                if minority.any()
                else None
            )
        result["splits"][name] = dict(samples=len(y), heads=metrics)
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--train", action="append", required=True)
    p.add_argument("--val", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--device", default="cuda")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--patience", type=int, default=8)
    p.add_argument("--length", type=int, default=64)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--hidden", type=int, default=384)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--seed", type=int, default=79)
    p.add_argument(
        "--edge-balance",
        action="store_true",
        help="train-only sqrt-frequency weights for ZR/ZL commands, cap8",
    )
    main(p.parse_args())
