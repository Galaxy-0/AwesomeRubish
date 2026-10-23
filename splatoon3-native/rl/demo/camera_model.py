"""Independent native +5 stick/gyro calibration, no match-trajectory fitting.

Fits only single-axis constant-input windows; full-stick speed is the
separate native +5 measurement. Camera transient filtering/physical gyro axes
remain qualified separately. Raw recordings and fitted coefficients stay private.
"""

import argparse
import json
from pathlib import Path
import numpy as np
from .convert import camera_windows
from .capture import write
from .build_host import sha


def predict(values, model):
    values = np.asarray(values, float)
    if model.get("kind") != "native_plus5_power_v1":
        return values @ np.asarray(model["matrix"]).T
    delta = values[..., 2:] @ np.asarray(model["gyro_matrix"]).T
    x = values[..., 0]
    delta[..., 0] -= (
        np.sign(x)
        * abs(x) ** model["stick_yaw_exponent"]
        * model["stick_full_yaw_rate"]
    )
    # Native gyro-enabled calibration has no independently established vertical
    # stick response. Retain a zero contribution instead of inventing pitch.
    return delta


def load_windows(source):
    p = Path(source)
    return camera_windows(
        [json.loads(x) for x in (p / "inputs-per-present.jsonl").open()],
        [json.loads(x) for x in (p / "native-barriers.jsonl").open()],
    )


def fit(source, calibration, out, validation):
    X, Y = load_windows(source)
    full = json.loads(Path(calibration).read_text())["config"][
        "stick_plus5_radians_per_frame"
    ]
    pure = (abs(X[:, 1:]) < 1e-8).all(-1) & (abs(X[:, 0]) > 0)
    groups = []
    for magnitude in sorted(set(abs(X[pure, 0]))):
        selected = pure & np.isclose(abs(X[:, 0]), magnitude)
        rate = float(np.median(-np.sign(X[selected, 0]) * Y[selected, 0]))
        if rate > 0 and magnitude < 1:
            groups.append(
                dict(input=float(magnitude), yaw_rate=rate, n=int(selected.sum()))
            )
    if len(groups) < 2:
        raise ValueError("two isolated stick amplitudes required")
    xx = np.log([g["input"] for g in groups])
    yy = np.log([g["yaw_rate"] / full for g in groups])
    exponent = float(xx @ yy / (xx @ xx))
    gm = np.zeros((2, 3))
    for axis in range(3):
        selected = (abs(X[:, :2]) < 1e-8).all(-1) & (abs(X[:, axis + 2]) > 1e-8)
        selected &= np.count_nonzero(abs(X[:, 2:]) > 1e-8, axis=1) == 1
        gm[:, axis] = np.median(Y[selected] / X[selected, axis + 2, None], axis=0)
    model = dict(
        source_sha256={
            str(p): sha(p)
            for p in [
                Path(source) / "inputs-per-present.jsonl",
                Path(source) / "native-barriers.jsonl",
                Path(calibration),
                Path(__file__),
            ]
        },
        kind="native_plus5_power_v1",
        source=str(source),
        native_full_anchor=str(calibration),
        stick_full_yaw_rate=full,
        stick_yaw_exponent=exponent,
        gyro_matrix=gm.tolist(),
        groups=groups,
        recommended_codebook="native_plus5",
        limitations=[
            "single-axis steady response only",
            "native gyro projection/cross-axis and transients at non-neutral pitch remain approximate",
            "physical controller gyro axis signs pending human check",
        ],
        validation={},
    )
    for name in [source, *validation]:
        x, y = load_windows(name)
        error = predict(x, model) - y
        model["validation"][str(name)] = dict(
            n=len(x), rmse_rad_frame=np.sqrt(np.mean(error**2, axis=0)).tolist()
        )
    write(Path(out), model)
    print(json.dumps(model, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True)
    p.add_argument(
        "--calibration", default="work/rl-stage0/native-camera-calibration-v1.json"
    )
    p.add_argument("--out", required=True)
    p.add_argument("--validation", action="append", default=[])
    a = p.parse_args()
    fit(a.source, a.calibration, a.out, a.validation)
