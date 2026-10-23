"""Short SSH polling with backoff; long jobs must be tmux/nohup scripts."""

import argparse, subprocess, time, sys


def ssh(command, *, attempts=6, sleep=time.sleep):
    delays = (30, 60, 120)
    for n in range(attempts):
        p = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=15",
                "-o",
                "ServerAliveInterval=10",
                "-o",
                "ServerAliveCountMax=2",
                "asuka0",
                command,
            ],
            text=True,
            capture_output=True,
        )
        if p.returncode != 255:
            return p
        print(p.stderr.strip(), file=sys.stderr, flush=True)
        if n + 1 < attempts:
            delay = delays[min(n, len(delays) - 1)]
            print(
                f"SSH transport unavailable; retry in {delay}s (not a milestone failure)",
                file=sys.stderr,
                flush=True,
            )
            sleep(delay)
    return p


if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("command")
    a.add_argument("--attempts", type=int, default=6)
    args = a.parse_args()
    r = ssh(args.command, attempts=args.attempts)
    print(r.stdout, end="")
    print(r.stderr, end="", file=sys.stderr)
    raise SystemExit(r.returncode)
