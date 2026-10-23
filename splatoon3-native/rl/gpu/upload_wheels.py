"""Resume private package-cache uploads in short SSH chunks, with SHA256.

Only public registry wheels are accepted. No game/save/geometry transfer here.
This can run locally under nohup; each remote command is a bounded append/hash.
"""

import argparse, hashlib, json, re, subprocess, tempfile, time, shlex
from pathlib import Path


def main(a):
    directory = Path(a.directory)
    files = sorted(directory.glob("*.whl"))
    if not files:
        raise ValueError("no completed wheels")
    remote = "splatoon3-native-rl-stage0/wheelhouse"
    with tempfile.TemporaryDirectory(prefix="rl0-package-ssh-") as tmp:
        socket = str(Path(tmp) / "master")
        options = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "ServerAliveInterval=10",
            "-o",
            "ServerAliveCountMax=2",
            "-o",
            "ControlMaster=auto",
            "-o",
            "ControlPersist=60",
            "-o",
            "ControlPath=" + socket,
            "asuka0",
        ]

        def call(command, payload=None):
            for attempt in range(8):
                try:
                    p = subprocess.run(
                        options + [command],
                        input=payload,
                        capture_output=True,
                        timeout=60,
                    )
                except subprocess.TimeoutExpired:
                    p = None
                if p is not None and p.returncode == 0:
                    return p.stdout.decode().strip()
                if p is not None:
                    print(p.stderr.decode(errors="replace"), flush=True)
                if attempt == 7:
                    raise RuntimeError(
                        "SSH transfer retries exhausted; partial files retained"
                    )
                time.sleep((30, 60, 120)[min(attempt, 2)])

        call('mkdir -p "$HOME/' + remote + '"')
        manifest = []
        for file in files:
            if not re.fullmatch(r"[A-Za-z0-9_.+\-]+\.whl", file.name):
                raise ValueError("unsafe wheel basename")
            size = file.stat().st_size
            digest = hashlib.file_digest(file.open("rb"), "sha256").hexdigest()
            path = '"$HOME/' + remote + "/" + file.name + '"'
            partial = '"$HOME/' + remote + "/" + file.name + '.partial"'
            got = call("if test -f " + path + "; then sha256sum " + path + "; fi")
            if got and got.split()[0] == digest:
                print(
                    json.dumps(dict(event="cache-hit", file=file.name, bytes=size)),
                    flush=True,
                )
                continue
            offset = int(
                call(
                    "if test -f "
                    + partial
                    + "; then wc -c < "
                    + partial
                    + "; else echo 0; fi"
                )
            )
            if offset > size:
                raise ValueError(
                    "remote partial larger than source, preserve and inspect"
                )
            started = time.monotonic()
            last = started
            with file.open("rb") as stream:
                while offset < size:
                    stream.seek(offset)
                    chunk = stream.read(4 * 1024 * 1024)
                    # Check expected offset before append. After a transport
                    # error, re-query actual bytes instead of duplicating data.
                    command = "python3 -c " + shlex.quote(
                        "import pathlib,sys; p=pathlib.Path.home()/"
                        + repr(remote + "/" + file.name + ".partial")
                        + "; n=p.stat().st_size if p.exists() else 0; expected="
                        + str(offset)
                        + '; assert n==expected,(n,expected); f=p.open("ab"); f.write(sys.stdin.buffer.read()); f.close()'
                    )
                    try:
                        p = subprocess.run(
                            options + [command],
                            input=chunk,
                            capture_output=True,
                            timeout=60,
                        )
                        if p.returncode != 0:
                            raise RuntimeError(p.stderr.decode(errors="replace"))
                        offset += len(chunk)
                    except (subprocess.TimeoutExpired, RuntimeError) as ex:
                        print(str(ex), flush=True)
                        time.sleep(30)
                        offset = int(
                            call(
                                "if test -f "
                                + partial
                                + "; then wc -c < "
                                + partial
                                + "; else echo 0; fi"
                            )
                        )
                    now = time.monotonic()
                    if now - last >= 10 or offset == size:
                        print(
                            json.dumps(
                                dict(
                                    event="upload",
                                    file=file.name,
                                    bytes=offset,
                                    total=size,
                                    seconds=round(now - started, 2),
                                )
                            ),
                            flush=True,
                        )
                        last = now
            got = call("sha256sum " + partial).split()[0]
            if got != digest:
                raise ValueError("remote wheel checksum mismatch; partial retained")
            call("mv " + partial + " " + path)
            manifest.append(dict(file=file.name, bytes=size, sha256=digest))
        Path(a.manifest).write_text(json.dumps(manifest, indent=2) + "\n")
        subprocess.run(
            ["ssh", "-o", "ControlPath=" + socket, "-O", "exit", "asuka0"],
            capture_output=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--directory", required=True)
    p.add_argument("--manifest", required=True)
    main(p.parse_args())
