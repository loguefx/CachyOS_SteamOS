#!/usr/bin/env python3
"""Find which report bits a Steam Controller (puck) uses for its buttons.

Reads the controller's hidraw nodes (read-only, alongside Steam) through timed
phases: hands off, then each button pressed three times. A button bit is one
that is quiet while idle and flips about six times (three presses, three
releases) in exactly one phase. Prints the result as JSON.

usage: tools/puck-capture.py [--seconds 6] [BUTTON ...]     (default: A B)
       tools/puck-capture.py Steam     -- press it slowly, a second apart, so
                                          it is never a double press
"""

import argparse
import json
import os
import select
import sys
import time

SYS_HIDRAW = "/sys/class/hidraw"


def valve_nodes():
    out = []
    for name in sorted(os.listdir(SYS_HIDRAW)):
        try:
            with open(os.path.join(SYS_HIDRAW, name, "device", "uevent")) as fh:
                if ":000028DE:" not in fh.read().upper():
                    continue
        except OSError:
            continue
        path = os.path.join("/dev", name)
        if os.access(path, os.R_OK):
            out.append(path)
    return out


def record(fds, seconds):
    """(path, report id, byte, bit) -> number of value changes."""
    flips, last = {}, {}
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        ready, _, _ = select.select(list(fds), [], [], 0.05)
        for fd in ready:
            try:
                raw = os.read(fd, 64)
            except OSError:
                continue
            if not raw:
                continue
            key = (fds[fd], raw[0])
            prev = last.get(key)
            last[key] = raw
            if prev is None or len(prev) != len(raw):
                continue
            for i in range(1, len(raw)):
                diff = prev[i] ^ raw[i]
                for bit in range(8):
                    if diff & (1 << bit):
                        k = (fds[fd], raw[0], i, bit)
                        flips[k] = flips.get(k, 0) + 1
    return flips


def countdown(text, seconds):
    print(f"\n>>> {text}  ({seconds:.0f}s)", flush=True)
    time.sleep(0.4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("buttons", nargs="*", default=["A", "B"])
    args = ap.parse_args()
    nodes = valve_nodes()
    if not nodes:
        print("no readable Valve hidraw node found", file=sys.stderr)
        return 1
    fds = {os.open(p, os.O_RDONLY | os.O_NONBLOCK): p for p in nodes}
    print("reading " + ", ".join(nodes))
    print("Wake the controller first (touch a stick, NOT the Steam button).")
    time.sleep(2)

    countdown("HANDS OFF the controller", 4)
    idle = record(fds, 4)
    phases = {}
    for name in args.buttons:
        countdown(f"Press {name} three times, slowly (a second apart)", args.seconds)
        phases[name] = record(fds, args.seconds)
    for fd in fds:
        os.close(fd)

    def buttons(name):
        others = [p for n, p in phases.items() if n != name]
        hits = []
        for k, n in phases[name].items():
            if idle.get(k) or any(o.get(k) for o in others):
                continue
            if 4 <= n <= 10:
                hits.append({"node": k[0], "report": f"0x{k[1]:02x}",
                             "byte": k[2], "bit": k[3], "changes": n})
        return sorted(hits, key=lambda h: (h["report"], h["byte"], h["bit"]))

    seen = set(idle)
    for p in phases.values():
        seen |= set(p)
    result = {name: buttons(name) for name in phases}
    result["reports_seen"] = sorted({f"0x{k[1]:02x}" for k in seen})
    print("\nRESULT " + json.dumps(result))
    if all(len(result[name]) == 1 for name in phases):
        print("Found one bit for each button.")
    else:
        print("Ambiguous or nothing found; the RESULT line shows every candidate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
