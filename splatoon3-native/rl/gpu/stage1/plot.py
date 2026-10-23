"""Offline scientific plots from owned CSV/JSONL; no game resources included."""

import argparse, csv, json
from pathlib import Path


def main(a):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = []
    matches = []
    for root in a.runs:
        root = Path(root)
        with (root / "metrics.csv").open() as f:
            rows.extend(csv.DictReader(f))
        if (root / "matches.jsonl").exists():
            matches.extend(
                json.loads(x) for x in (root / "matches.jsonl").read_text().splitlines()
            )
    rows.sort(key=lambda r: int(r["environment_frames"]))
    matches.sort(key=lambda r: r["frames"])
    x = [int(r["environment_frames"]) / 1e6 for r in rows]
    fig, axes = plt.subplots(3, 2, figsize=(13, 10), constrained_layout=True)
    for key, color in [("entropy", "#286ba6"), ("approx_kl", "#ca6d27")]:
        ax = axes[0, 0] if key == "entropy" else axes[0, 1]
        ax.plot(x, [float(r[key]) for r in rows], color=color, lw=1.2)
        ax.set_title(key)
    for key, color in [("value_loss", "#3c8d61"), ("grad_norm", "#b24c75")]:
        ax = axes[1, 0] if key == "value_loss" else axes[1, 1]
        ax.plot(x, [float(r[key]) for r in rows], color=color, lw=1.2)
        ax.set_title(key)
    mx = [r["frames"] / 1e6 for r in matches]
    for i, (name, color) in enumerate([("Stamper", "#a63872"), (".52", "#308e79")]):
        axes[2, 0].plot(
            mx, [r["turf_percent"][i] for r in matches], color=color, label=name
        )
        axes[2, 1].plot(
            mx,
            [r.get("weapon_kills", [0, 0])[i] for r in matches],
            color=color,
            label=name,
        )
    axes[2, 0].set_title("Training-cohort mean turf (%)")
    axes[2, 1].set_title("Attributed weapon KOs (falls excluded)")
    for ax in axes.flat:
        ax.set_xlabel("Environment frames (million)")
        ax.grid(alpha=0.2)
    axes[2, 0].legend()
    axes[2, 1].legend()
    fig.suptitle(
        "Stage1 primary-only PPO: training diagnostics, not held-out win rates"
    )
    dest = Path(a.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(dest, dpi=160)
    plt.close(fig)
    print(json.dumps(dict(path=str(dest), updates=len(rows), matches=len(matches))))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--runs", nargs="+", required=True)
    p.add_argument("--out", required=True)
    main(p.parse_args())
