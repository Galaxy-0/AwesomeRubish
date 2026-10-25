"""Recurrent PPO with frozen-BC categorical KL and per-head diagnostics."""

import torch
from ..stage1.ppo import gae, sequences
from .model import distributions, bc_kl


def update(
    model,
    optimizer,
    batch,
    bootstrap,
    *,
    bc_coef,
    entropy_coef,
    zr_entropy=0.005,
    sequence=32,
    minibatch=16,
    epochs=3,
    gamma=0.9995,
    lam=0.95,
    target_kl=0.025,
    critic_only=False,
):
    adv, returns = gae(
        batch["rewards"], batch["values"], batch["after"], bootstrap, gamma, lam
    )
    raw_std = adv.std(unbiased=False)
    adv = (adv - adv.mean()) / raw_std.clamp_min(0.05)
    view = {k: sequences(v, sequence) for k, v in batch["obs"].items()}
    parts = {
        k: sequences(v, sequence)
        for k, v in dict(
            actions=batch["actions"],
            old=batch["logprob"],
            oldheads=batch["heads"],
            returns=returns,
            adv=adv,
            before=batch["before"],
            teacher=batch["teacher"],
            oldvalue=batch["values"],
        ).items()
    }
    hidden = (
        batch["hidden"][::sequence].transpose(0, 1).reshape(1, -1, model.hidden_size)
    )
    rows, heads = [], []
    stopped = False
    for epoch in range(epochs):
        for ids in torch.randperm(hidden.shape[1], device=hidden.device).split(
            minibatch
        ):
            logits, value, _ = model(
                {k: x[:, ids] for k, x in view.items()},
                hidden[:, ids],
                parts["before"][:, ids],
            )
            dist = distributions(logits)
            logs = dist.log_prob(parts["actions"][:, ids])
            entropy = dist.entropy()
            logratio = logs.sum(-1) - parts["old"][:, ids]
            ratio = logratio.exp()
            kl = ((ratio - 1) - logratio).mean()
            if not torch.isfinite(kl):
                raise FloatingPointError("nonfinite PPO KL")
            if float(kl.detach()) > target_kl:
                stopped = True
                break
            policy_loss = torch.maximum(
                -parts["adv"][:, ids] * ratio,
                -parts["adv"][:, ids] * ratio.clamp(0.8, 1.2),
            ).mean()
            clipped = parts["oldvalue"][:, ids] + (
                value - parts["oldvalue"][:, ids]
            ).clamp(-0.2, 0.2)
            vloss = (
                0.5
                * torch.maximum(
                    (value - parts["returns"][:, ids]).square(),
                    (clipped - parts["returns"][:, ids]).square(),
                ).mean()
            )
            regularizer = bc_kl(logits, parts["teacher"][:, ids].float()).mean()
            objective = (
                policy_loss
                + 0.5 * vloss
                + bc_coef * regularizer
                - entropy_coef * entropy[..., :6].sum(-1).mean()
                - zr_entropy * entropy[..., 3].mean()
            )
            if critic_only:
                objective = vloss
            if not torch.isfinite(objective):
                raise FloatingPointError("nonfinite PPO objective")
            optimizer.zero_grad(set_to_none=True)
            objective.backward()
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 0.5)
            if not torch.isfinite(norm):
                raise FloatingPointError("nonfinite gradients")
            optimizer.step()
            with torch.no_grad():
                head_delta = logs - parts["oldheads"][:, ids]
                hk = (head_delta.exp() - 1 - head_delta).mean((0, 1))
                heads.append(torch.cat([entropy.mean((0, 1)), hk]))
                rows.append(
                    torch.stack(
                        [
                            policy_loss.detach(),
                            vloss.detach(),
                            regularizer.detach(),
                            kl.detach(),
                            norm.detach(),
                            ((ratio - 1).abs() > 0.2).float().mean(),
                        ]
                    )
                )
        if stopped:
            break
    result = (
        dict(
            zip(
                [
                    "policy_loss",
                    "value_loss",
                    "bc_kl",
                    "approx_kl",
                    "grad_norm",
                    "clip_fraction",
                ],
                torch.stack(rows).mean(0).cpu().tolist(),
            )
        )
        if rows
        else dict(
            policy_loss=0.0,
            value_loss=0.0,
            bc_kl=0.0,
            approx_kl=float(kl),
            grad_norm=0.0,
            clip_fraction=0.0,
        )
    )
    result.update(
        early_kl_stop=stopped,
        optimization_steps=len(rows),
        advantage_std=float(raw_std),
        advantage_divisor=float(raw_std.clamp_min(0.05)),
    )
    hs = torch.stack(heads).mean(0).cpu().tolist() if heads else [0.0] * 16
    for i, name in enumerate(["move", "yaw", "pitch", "ZR", "ZL", "B", "R", "RS"]):
        result["entropy_" + name], result["kl_" + name] = hs[i], hs[8 + i]
    if not all(torch.isfinite(p).all() for p in model.parameters()):
        raise FloatingPointError("nonfinite model")
    return result
