"""Private replay QA page. Uses the existing showcase without publishing it."""

import argparse, json, re
from pathlib import Path


def main(a):
    page = Path(a.showcase).read_text()
    pattern = r'(<script[^>]*id="showcase-data"[^>]*>)(.*?)(</script>)'
    match = re.search(pattern, page, re.S)
    if not match:
        raise ValueError("existing generated showcase-data not found")
    data = json.loads(match[2])
    trace = json.loads(Path(a.trace).read_text())
    trace.pop("referee_samples", None)
    data["traces"] = [trace] + data["traces"]
    page = (
        page[: match.start(2)]
        + json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace(
            "</", "<\\/"
        )
        + page[match.end(2) :]
    )
    page = page.replace(
        "'S1 · 模拟状态'",
        "clip.source_kind==='gpu_simulated_state'?'GPU · RL 随机夹具':'S1 · 模拟状态'",
    )
    out = Path(a.out).resolve()
    if "work" not in out.parts:
        raise ValueError("QA output must remain private under work/")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print(json.dumps(dict(path=str(out), bytes=out.stat().st_size, clip=trace["id"])))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--showcase", default="showcase/index.html")
    p.add_argument("--trace", required=True)
    p.add_argument("--out", required=True)
    main(p.parse_args())
