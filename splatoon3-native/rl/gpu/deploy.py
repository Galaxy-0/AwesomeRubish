"""Copy only allowlisted GPU source and private derived data to the own account.

No native host, assets, saves, policies or sibling project directories included.
Versioned uploads preserve previous remote source/data; long jobs run in tmux.
"""

import argparse, io, tarfile, subprocess, time, sys, json, hashlib
from pathlib import Path
from .remote import ssh


def main(a):
    if not a.version.replace("-", "").isalnum():
        raise ValueError("simple version name required")
    root = Path(__file__).resolve().parents[2]
    source = root / "rl/gpu"
    data = Path(a.data).resolve()
    if not data.is_relative_to(root / "work"):
        raise ValueError("private data must be under work/")
    parameters = json.loads((data / "parameters.json").read_text())
    if (
        hashlib.sha256((data / "map.npz").read_bytes()).hexdigest()
        != parameters["map_export_sha256"]
    ):
        raise ValueError("private data checksum mismatch")
    allowed = list(source.glob("*.py")) + [
        source / "README.md",
        source / "contract.py",
        data / "map.npz",
        data / "parameters.json",
    ]
    for extra in [a.references, a.calibration]:
        if extra:
            extra = Path(extra).resolve()
            if not extra.is_relative_to(root / "work"):
                raise ValueError("private extra must be under work/")
            allowed.append(extra)
    allowed = sorted(set(allowed))
    payload = io.BytesIO()
    manifest = {}
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for p in allowed:
            name = ("data/" + p.name) if p.parent != source else ("src/gpu/" + p.name)
            archive.add(p, arcname=name, recursive=False)
            manifest[name] = hashlib.sha256(p.read_bytes()).hexdigest()
        meta = json.dumps(manifest, indent=2).encode()
        info = tarfile.TarInfo("sha256.json")
        info.size = len(meta)
        archive.addfile(info, io.BytesIO(meta))
    dest = "splatoon3-native-rl-stage0/" + a.version
    r = ssh('mkdir -p "$HOME/' + dest + '" && chmod 700 "$HOME/' + dest + '"')
    print(r.stdout)
    r.check_returncode()
    for n in range(6):
        p = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=15",
                "asuka0",
                'tar -xzf - -C "$HOME/' + dest + '"',
            ],
            input=payload.getvalue(),
            capture_output=True,
        )
        if p.returncode == 0:
            break
        print(p.stderr.decode(errors="replace"), file=sys.stderr, flush=True)
        if n == 5:
            raise SystemExit(p.returncode)
        time.sleep((30, 60, 120)[min(n, 2)])
    print(
        json.dumps(
            dict(remote=dest, archive_bytes=len(payload.getvalue()), files=manifest)
        ),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True)
    p.add_argument("--data", required=True)
    p.add_argument("--references")
    p.add_argument("--calibration")
    main(p.parse_args())
