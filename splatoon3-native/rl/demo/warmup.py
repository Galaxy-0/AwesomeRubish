"""Private PSO manifest assembly for full-render human recording.

A short scripted run need not encounter combat/death/map shaders. Reuse both
perspectives of the most recent human recording, including inherited manifests;
keep every original intact. This is coverage reuse, not proof of zero cold misses.
"""

from pathlib import Path
import json
import time


def assemble(seed, sessions, role, output, shader_manifest=None):
    sources = [Path(seed)]
    for session in sessions:
        # Identical content-addressed pipeline keys are safe across perspectives.
        for peer in (role, 1 - role):
            sources.extend(
                Path(session) / name
                for name in (f"warm-{peer}.tsv", f"player-{peer}/pso_user.tsv")
            )
    lines = {}
    provenance = []
    for path in dict.fromkeys(sources):
        if not path.is_file():
            continue
        count = 0
        for line in path.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if (
                fields[0] not in ("S", "R", "C")
                or len(fields) < 2
                or (fields[0] == "S" and len(fields) != 3)
            ):
                raise ValueError(f"invalid warm manifest record in {path}")
            lines[line] = None
            count += 1
        provenance.append(dict(path=str(path), records=count))
    if shader_manifest:
        path = Path(shader_manifest)
        count = 0
        for line in path.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if (
                len(fields) != 3
                or fields[0] != "S"
                or fields[2] not in ("0", "1", "3", "4", "5")
            ):
                raise ValueError(
                    "additional warm manifest must contain only shader records"
                )
            lines[line] = None
            count += 1
        provenance.append(dict(path=str(path), records=count))
    output = Path(output)
    output.write_text("\n".join(lines) + "\n")
    counts = {kind: sum(x.startswith(kind + "\t") for x in lines) for kind in "SRC"}
    audit = dict(
        role=role,
        records=len(lines),
        counts=counts,
        sources=provenance,
        limitation="Observed coverage only. Unseen game effects can still compile; no zero-stall guarantee.",
    )
    output.with_suffix(".json").write_text(json.dumps(audit, indent=2) + "\n")
    return audit


def collect_shaders(corpus, output):
    """Merge only previously observed S keys; don't load every old pipeline.

    Whole-match input replay is not deterministic in every render effect variant.
    Extra library coverage avoids repeatedly rediscovering known variants, while
    keeping render PSO count below the renderer's bounded cache capacity.
    """
    output = Path(output)
    if output.exists():
        raise ValueError("fresh output required")
    keys = set()
    files = sorted(Path(corpus).rglob("pso_user.tsv"))
    for path in files:
        with path.open() as stream:
            for line in stream:
                if line.startswith("S\t"):
                    keys.add(line.strip())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(sorted(keys)) + "\n")
    return dict(files=len(files), shaders=len(keys), output=str(output))


def wait_ready(hosts, timeout, cancelled=lambda: False, check=lambda: None):
    """Called with native clients at their initial barrier and clock paused.

    Waiting for the compiler is loading time, never a neutral game step or a
    slow-motion segment in the user's controlled battle. Keep the original
    process/watchdog ownership and permit cancellation/resource stops.
    """
    start = time.monotonic()
    pending = {n: (process, directory) for n, process, directory in hosts}
    while pending:
        if cancelled():
            raise InterruptedError("demo cancelled during shader warm-up")
        check()
        for n, (process, directory) in list(pending.items()):
            if process.poll() is not None:
                raise RuntimeError(f"demo host {n} exited during shader warm-up")
            text = (Path(directory) / "host.log").read_text(errors="replace")
            if "管线预热完成：" in text:
                pending.pop(n)
        if not pending:
            break
        if time.monotonic() - start >= timeout:
            raise TimeoutError(
                f"demo shader warm-up incomplete: players {sorted(pending)}"
            )
        time.sleep(0.1)
    return dict(
        ready=True,
        wait_seconds=time.monotonic() - start,
        scope="before first controlled input, shared clock paused",
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--shader-corpus", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    from .capture import safe_out

    print(
        json.dumps(
            collect_shaders(safe_out(a.shader_corpus), safe_out(a.out)), indent=2
        )
    )
