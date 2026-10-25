"""Level-control BC ablations with event-weighted futures and attack auxiliary."""

import argparse
import json
import time
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
from .model import Actor

OBS = (
    "screen",
    "entities",
    "entity_mask",
    "hud",
    "minimap",
    "weapon",
    "action_mask",
    "previous_actions",
    "quality",
)


def dataset(path):
    with np.load(Path(path) / "prepared.npz") as z:
        return {k: torch.as_tensor(z[k].copy()) for k in z.files}


def chunks(d, length, horizon):
    span = length + horizon - 1
    f = d["frame"]
    return [
        s
        for s in range(0, len(f) - span + 1, 32)
        if bool(((f[s + 1 : s + span] - f[s : s + span - 1]) == 2).all())
    ]


def loss(logits, labels, event, class_weights):
    terms = []
    for h in range(6):
        scores = F.cross_entropy(
            logits[..., h, :].reshape(-1, 17),
            labels[..., h].reshape(-1),
            reduction="none",
            weight=class_weights[h],
        ).reshape(labels.shape[:-1])
        w = event[..., h]
        terms.append(
            (scores * w).sum()
            / (w * class_weights[h, labels[..., h]]).sum().clamp_min(1)
        )
    return torch.stack(terms).mean()


@torch.no_grad()
def score(model, d, device):
    hidden = model.initial(1, device)
    logits = []
    aux = []
    for s in range(0, len(d["frame"]), 128):
        obs = {k: d[k][s : s + 128, None].to(device) for k in OBS}
        reset = torch.zeros(len(obs["hud"]), 1, device=device, dtype=torch.bool)
        if s == 0:
            reset[0] = True
        frames = d["frame"][max(0, s - 1) : s + 128]
        gap = (frames[1:] - frames[:-1]) != 2
        if s == 0:
            reset[1:, 0] = gap.to(device)
        else:
            reset[:, 0] = gap.to(device)
        scores, _, hidden, a = model(obs, hidden, reset)
        logits.append(scores[:, 0].cpu())
        aux.append(a[:, 0].cpu())
    return torch.cat(logits), torch.cat(aux)


def metrics(logits, labels):
    result = {}
    for h, name in enumerate(("move", "yaw", "pitch", "ZR", "ZL", "B")):
        scores = logits[:, 0, h]
        y = labels[:, h]
        result[name] = dict(
            accuracy=float((scores.argmax(-1) == y).float().mean()),
            ce=float(F.cross_entropy(scores, y)),
        )
    return result


def main(a):
    torch.set_num_threads(2)
    torch.set_float32_matmul_precision("high")
    torch.manual_seed(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    if str(Path(a.val).resolve()) in {str(Path(p).resolve()) for p in a.train}:
        raise ValueError("match leakage")
    train = [dataset(p) for p in a.train]
    val = dataset(a.val)
    model = Actor(a.hidden, a.horizon, a.feedback).to(a.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    cw = torch.ones(8, 17)
    y = torch.cat([d["labels"] for d in train])
    for h, size in enumerate((17, 9, 9, 2, 2, 2)):
        counts = torch.bincount(y[:, h], minlength=17).float()
        cw[h, :size] = (counts.max() / counts[:size].clamp_min(1)).sqrt().clamp_max(4)
    cw = cw.to(a.device)
    starts = [
        (i, s) for i, d in enumerate(train) for s in chunks(d, a.length, a.horizon)
    ]
    weights = torch.tensor(
        [
            1.0
            + 2 * bool(train[i]["encounter"][s : s + a.length].any())
            + bool((train[i]["attack"][s : s + a.length] >= 2).any())
            for i, s in starts
        ]
    )
    best = float("inf")
    stale = 0
    wall = time.perf_counter()
    (out / "config.json").write_text(json.dumps(vars(a), indent=2) + "\n")
    for epoch in range(1, a.epochs + 1):
        model.train()
        total = 0
        steps = 0
        order = torch.multinomial(weights, len(starts), replacement=True).tolist()
        for at in range(0, len(order), a.batch):
            picked = [starts[i] for i in order[at : at + a.batch]]
            obs = {
                k: torch.stack(
                    [train[i][k][s : s + a.length] for i, s in picked], 1
                ).to(a.device)
                for k in OBS
            }
            targets = torch.stack(
                [
                    torch.stack(
                        [
                            train[i]["labels"][s + k : s + k + a.length]
                            for k in range(a.horizon)
                        ],
                        1,
                    )
                    for i, s in picked
                ],
                1,
            ).to(a.device)
            ev = torch.stack(
                [
                    torch.stack(
                        [
                            train[i]["event_weights"][s + k : s + k + a.length]
                            for k in range(a.horizon)
                        ],
                        1,
                    )
                    for i, s in picked
                ],
                1,
            ).to(a.device)
            attack = torch.stack(
                [train[i]["attack"][s : s + a.length] for i, s in picked], 1
            ).to(a.device)
            scores, _, _, extra = model(obs, model.initial(len(picked), a.device))
            objective = loss(scores, targets, ev, cw) + 0.15 * F.cross_entropy(
                extra.reshape(-1, 4), attack.reshape(-1)
            )
            optimizer.zero_grad(set_to_none=True)
            objective.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
            optimizer.step()
            total += float(objective.detach())
            steps += 1
        logits, aux = score(model.eval(), val, a.device)
        n = len(logits) - a.horizon + 1
        target = torch.stack([val["labels"][k : k + n] for k in range(a.horizon)], 1)
        ev = torch.stack([val["event_weights"][k : k + n] for k in range(a.horizon)], 1)
        selection = float(loss(logits[:n], target, ev, cw.cpu()))
        row = dict(
            epoch=epoch,
            train_loss=total / max(1, steps),
            selection=selection,
            heads=metrics(logits, val["labels"]),
            seconds=time.perf_counter() - wall,
        )
        with (out / "curves.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)
        if selection < best - 1e-4:
            best = selection
            stale = 0
            torch.save(
                dict(
                    schema="inklab.bc2.checkpoint.v1",
                    policy=model.state_dict(),
                    hidden=a.hidden,
                    horizon=a.horizon,
                    feedback=a.feedback,
                    epoch=epoch,
                    config=vars(a),
                ),
                out / "best.pt",
            )
        else:
            stale += 1
        if stale >= a.patience:
            break
    r = torch.load(out / "best.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(r["policy"])
    result = dict(
        schema="inklab.bc2.fit.v1",
        best_epoch=r["epoch"],
        epochs=epoch,
        seconds=time.perf_counter() - wall,
        parameters=sum(p.numel() for p in model.parameters()),
        peak_cuda_mib=torch.cuda.max_memory_allocated() / 2**20
        if a.device == "cuda"
        else 0,
        config=vars(a),
        splits={},
    )
    for name, matches in [("train", train), ("val", [val])]:
        ls = []
        ys = []
        for d in matches:
            scores, _ = score(model, d, a.device)
            ls.append(scores)
            ys.append(d["labels"])
        result["splits"][name] = metrics(torch.cat(ls), torch.cat(ys))
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--train", action="append", required=True)
    p.add_argument("--val", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--horizon", type=int, default=1)
    p.add_argument("--feedback", action="store_true")
    p.add_argument("--hidden", type=int, default=384)
    p.add_argument("--seed", type=int, default=80)
    p.add_argument("--length", type=int, default=64)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--patience", type=int, default=12)
    p.add_argument("--lr", type=float, default=0.0003)
    p.add_argument("--device", default="cuda")
    main(p.parse_args())
