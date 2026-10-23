"""Fresh opt-in diagnostic build; protected hosts/sources are never overwritten."""

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main(out):
    factory = ROOT / "tools/zipcaster_d3r/build.py"
    text = factory.read_text()

    def change(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError("factory identity/shape changed: " + old[:80])
        text = text.replace(old, new, 1)

    change(
        "shutil.copy2(Path(__file__).with_name('test_aim.h'),aim)",
        "aim.write_text((ROOT/'tools/zipcaster_d3r/test_aim.h').read_text()+'\\n'+(ROOT/'rl/gpu/camera_sensor.h').read_text())",
    )
    change(
        r"d3r_update(player,slot,health);\n",
        r"d3r_update(player,slot,health);r0_camera_state();\n",
    )
    change(
        "gate_obs_set(50,d3r_camera_compute);",
        "gate_obs_set(50,d3r_camera_compute);gate_obs_set(51,r0_input_options);",
    )
    # The original factory already increases OBS_MAX to52, allowing gate51.
    opcode = 0x395B6268  # rewrite.py independently checks the original NSO word
    needle = "'28c4287aee36f7499da60f3e68b54c70': [\n"
    addition = f"    (0x2f5d250,51,'{opcode:08x}','R0 temporary native input options before normal conversion'),\n"
    change(
        "rewrite.write_text(base)",
        "base=base.replace("
        + repr(needle)
        + ","
        + repr(needle + addition)
        + ",1);rewrite.write_text(base)",
    )
    change(
        "Path(__file__).with_name('test_aim.h')};frozen=",
        "Path(__file__).with_name('test_aim.h'),ROOT/'rl/gpu/camera_sensor.h',Path("
        + repr(str(Path(__file__).resolve()))
        + ")};frozen=",
    )
    scope = dict(__name__="private_rl0_probe_factory", __file__=str(factory))
    exec(compile(text, str(factory), "exec"), scope)
    scope["main"](SimpleNamespace(out=Path(out)))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    main(p.parse_args().out)
