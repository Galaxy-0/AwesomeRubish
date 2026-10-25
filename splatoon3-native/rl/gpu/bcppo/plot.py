"""Offline numeric curves only; generated plots stay private, outside git."""

import argparse
import csv
import json
from pathlib import Path
import numpy as np


def main(a):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    root = Path(a.root)
    rows = list(csv.DictReader((root / "metrics.csv").open()))
    x = np.array([float(r["wall_seconds"]) / 60 for r in rows])
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), constrained_layout=True)

    def curve(ax, key, label, color):
        y = np.array([float(r[key]) for r in rows])
        ax.plot(x, y, color=color, alpha=0.15, lw=0.5)
        window = min(20, len(y))
        ax.plot(
            x[window - 1 :],
            np.convolve(y, np.ones(window) / window, "valid"),
            label=label,
            color=color,
        )

    for ax, spec in zip(
        axes.flat,
        [
            [
                ("approx_kl", "PPO joint KL", "#235fa5"),
                ("bc_kl", "BC prior mean KL", "#a65c16"),
            ],
            [("value_loss", "Value loss", "#238268")],
            [
                ("attacks_per_minute", "All attacks/min", "#235fa5"),
                ("full_per_minute", "Full releases/min", "#a65c16"),
            ],
            [
                ("zr_fraction", "ZR held fraction", "#235fa5"),
                ("entropy_ZR", "ZR entropy (nats)", "#a65c16"),
            ],
            [
                ("visible_fraction", "Enemy visible fraction", "#238268"),
                ("pitch_clamped_fraction", "Pitch clamped fraction", "#9b3b5c"),
            ],
            [],
        ],
    ):
        for key, label, color in spec:
            curve(ax, key, label, color)
    matches = [json.loads(s) for s in (root / "matches.jsonl").read_text().splitlines()]
    n = json.loads((root / "config.json").read_text())["n_envs"]
    mx = [r["elapsed"] / 60 for r in matches]
    axes[2, 1].plot(
        mx,
        [r["weapon_kills"] / n for r in matches],
        label="Training KO/game (mixed starts)",
    )
    axes[2, 1].plot(
        mx,
        [r["damage"] / n / 100 for r in matches],
        label="Training damage/game /100",
        alpha=0.7,
    )
    for ax, title in zip(
        axes.flat,
        [
            "Policy drift",
            "Value fit",
            "Weapon output",
            "ZR exploration",
            "View / pose",
            "Training combat (not acceptance)",
        ],
    ):
        ax.set_title(title)
        ax.set_xlabel("Elapsed minutes (includes preheat/eval)")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    axes[0, 1].set_yscale("log")
    fig.suptitle(
        "BC warm-start PPO startup: rolling20 updates; normal-spawn acceptance reported separately"
    )
    dest = Path(a.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--out", required=True)
    main(p.parse_args())
