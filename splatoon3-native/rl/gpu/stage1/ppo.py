"""Recurrent clipped PPO, zero-sum rewards and masked historical transitions."""

import torch


def gae(rewards, values, dones, bootstrap, gamma=0.9995, lam=0.95):
    advantage = torch.zeros_like(rewards)
    last = torch.zeros_like(bootstrap)
    for t in reversed(range(len(rewards))):
        next_value = bootstrap if t == len(rewards) - 1 else values[t + 1]
        live = (~dones[t]).float()
        delta = rewards[t] + gamma * live * next_value - values[t]
        last = delta + gamma * lam * live * last
        advantage[t] = last
    return advantage, advantage + values


def sequences(value, length):
    t, b = value.shape[:2]
    if t % length:
        raise ValueError("rollout must divide into complete recurrent sequences")
    v = value.reshape(t // length, length, b, *value.shape[2:])
    return v.transpose(0, 1).reshape(length, t // length * b, *value.shape[2:])


def update(
    policy,
    optimizer,
    batch,
    bootstrap,
    *,
    sequence_length=32,
    minibatch_sequences=64,
    epochs=3,
    clip=0.2,
    gamma=0.9995,
    lam=0.95,
    entropy_coef=0.0015,
    value_coef=0.5,
    target_kl=0.04,
):
    advantages, returns = gae(
        batch["rewards"], batch["values"], batch["done_after"], bootstrap, gamma, lam
    )
    learn = batch["learn"].float()
    count = learn.sum().clamp_min(1)
    mean = (advantages * learn).sum() / count
    std = ((advantages - mean).square() * learn).sum().div(count).sqrt().clamp_min(1e-6)
    advantages = (advantages - mean) / std
    obs = {k: sequences(v, sequence_length) for k, v in batch["obs"].items()}
    oldlog = sequences(batch["logprob"], sequence_length)
    oldvalue = sequences(batch["values"], sequence_length)
    adv = sequences(advantages, sequence_length)
    ret = sequences(returns, sequence_length)
    mask = sequences(learn, sequence_length)
    done = sequences(batch["done_before"], sequence_length)
    actions = sequences(batch["actions"], sequence_length)
    hidden = (
        batch["hidden"][::sequence_length]
        .transpose(0, 1)
        .reshape(1, -1, policy.hidden_size)
    )
    eligible = (mask.sum(0) > 0).nonzero().flatten()
    total = len(eligible)
    stats = []
    early = False
    if total == 0:
        return dict(
            policy_loss=0.0,
            value_loss=0.0,
            entropy=0.0,
            approx_kl=0.0,
            clip_fraction=0.0,
            grad_norm=0.0,
            early_stop_kl=False,
            optimization_steps=0,
            advantage_mean=float(mean.item()),
            advantage_std=float(std.item()),
            finite=True,
        )
    for epoch in range(epochs):
        order = eligible[torch.randperm(total, device=mask.device)]
        for ids in order.split(minibatch_sequences):
            w = mask[:, ids]
            den = w.sum().clamp_min(1)
            view = {k: v[:, ids] for k, v in obs.items()}
            newlog, entropy, value = policy.sequence(
                view, hidden[:, ids], done[:, ids], actions[:, ids]
            )
            logratio = newlog - oldlog[:, ids]
            ratio = logratio.exp()
            pg = torch.maximum(
                -adv[:, ids] * ratio, -adv[:, ids] * ratio.clamp(1 - clip, 1 + clip)
            )
            loss_policy = (pg * w).sum() / den
            clipped = oldvalue[:, ids] + (value - oldvalue[:, ids]).clamp(-clip, clip)
            loss_value = (
                0.5
                * (
                    torch.maximum(
                        (value - ret[:, ids]).square(), (clipped - ret[:, ids]).square()
                    )
                    * w
                ).sum()
                / den
            )
            ent = (entropy * w).sum() / den
            loss = loss_policy + value_coef * loss_value - entropy_coef * ent
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            norm = torch.nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
            optimizer.step()
            with torch.no_grad():
                kl = (((ratio - 1) - logratio) * w).sum() / den
                clipped_fraction = (((ratio - 1).abs() > clip) * w).sum() / den
            stats.append(
                torch.stack(
                    [
                        loss_policy.detach(),
                        loss_value.detach(),
                        ent.detach(),
                        kl,
                        clipped_fraction,
                        norm.detach(),
                    ]
                )
            )
        # Once per epoch, not per frame; no cross-episode recurrent leakage.
        if (
            float(
                torch.stack(stats)[-max(1, total // minibatch_sequences) :, 3]
                .mean()
                .item()
            )
            > target_kl
        ):
            early = True
            break
    result = dict(
        zip(
            [
                "policy_loss",
                "value_loss",
                "entropy",
                "approx_kl",
                "clip_fraction",
                "grad_norm",
            ],
            torch.stack(stats).mean(0).cpu().tolist(),
        )
    )
    result.update(
        early_stop_kl=early,
        optimization_steps=len(stats),
        advantage_mean=float(mean.item()),
        advantage_std=float(std.item()),
        finite=all(torch.isfinite(p).all().item() for p in policy.parameters()),
    )
    return result
