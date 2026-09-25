#!/usr/bin/env python3
"""Player one: cachy-console-pads against a stand-in Steam client.

The real helper speaks to the Steam client's DevTools port. Here that port is
a small fake that holds a controller list and a PlayStation setting, and
answers the handful of expressions the helper evaluates, so the reorder and
the save-and-restore of the setting can be driven without a Steam client.
"""

import base64
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "bin", "cachy-console-pads")

loader = importlib.machinery.SourceFileLoader("pads", TARGET)
spec = importlib.util.spec_from_loader("pads", loader)
pads = importlib.util.module_from_spec(spec)
loader.exec_module(pads)

FAILURES = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        got  = {got!r}")
        print(f"        want = {want!r}")
        FAILURES.append(label)


STEAM_CONTROLLER = {"index": 1, "type": 10, "name": "Steam Controller"}
DUALSENSE = {"index": 5, "type": 45, "name": "DualSense Wireless Controller"}
XBOX = {"index": 6, "type": 32, "name": "Xbox Wireless Controller"}


def pad(base, slot):
    return dict(base, slot=slot)


def decode_varint(data, pos):
    n = shift = 0
    while True:
        b = data[pos]
        pos += 1
        n |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return n, pos


class FakeSteam:
    """Enough of the client's SharedJSContext for the helper."""

    def __init__(self, controllers, ps_support=1):
        self.controllers = controllers
        self.ps_support = ps_support
        self.swaps = []
        self.conns = set()
        self.lock = threading.Lock()
        fake = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                fake.serve(self.request)

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.server = Server(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        # Like the client exiting: every open connection goes with it.
        for conn in list(self.conns):
            try:
                conn.shutdown(socket.SHUT_RDWR)
                conn.close()
            except OSError:
                pass

    def evaluate(self, expr):
        with self.lock:
            if expr.startswith("typeof SteamClient"):
                return True
            if "m_controllerList" in expr:
                return [dict(c) for c in self.controllers]
            if "controller_ps_support" in expr:
                return self.ps_support
            m = re.match(r"SteamClient\.Settings\.SetSetting\('([^']*)'\)", expr)
            if m:
                data = base64.b64decode(m.group(1))
                tag, pos = decode_varint(data, 0)
                value, _ = decode_varint(data, pos)
                if tag >> 3 == 14003:
                    self.ps_support = value
                return None
            m = re.match(r"SteamClient\.Input\.SwapControllerOrder\((-?\d+),(-?\d+)\)", expr)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                self.swaps.append((a, b))
                for c in self.controllers:
                    if c["slot"] == a:
                        c["slot"] = b
                    elif c["slot"] == b:
                        c["slot"] = a
                return None
            raise ValueError(f"unexpected expression: {expr[:60]}")

    def serve(self, conn):
        self.conns.add(conn)
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = conn.recv(4096)
            if not chunk:
                return
            head += chunk
        request = head.decode(errors="replace")
        path = request.split(" ", 2)[1]
        if path == "/json":
            body = json.dumps([{"title": "SharedJSContext", "type": "page",
                                "webSocketDebuggerUrl":
                                f"ws://127.0.0.1:{self.port}/devtools/page/X"}]).encode()
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
            return
        key = re.search(r"Sec-WebSocket-Key: (\S+)", request).group(1)
        accept = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        buf = head.split(b"\r\n\r\n", 1)[1]

        def read(n):
            nonlocal buf
            while len(buf) < n:
                chunk = conn.recv(65536)
                if not chunk:
                    raise ConnectionError
                buf += chunk
            out, buf = buf[:n], buf[n:]
            return out

        try:
            while True:
                b0, b1 = read(2)
                n = b1 & 0x7F
                if n == 126:
                    n = struct.unpack("!H", read(2))[0]
                elif n == 127:
                    n = struct.unpack("!Q", read(8))[0]
                mask = read(4)
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(read(n)))
                msg = json.loads(data)
                value = self.evaluate(msg["params"]["expression"])
                reply = json.dumps({"id": msg["id"], "result": {
                    "result": {"type": "object", "value": value}}}).encode()
                if len(reply) < 126:
                    hdr = struct.pack("!BB", 0x81, len(reply))
                else:
                    hdr = struct.pack("!BBH", 0x81, 126, len(reply))
                conn.sendall(hdr + reply)
        except (ConnectionError, OSError, ValueError):
            pass


class World:
    def __init__(self, controllers, ps_support=1):
        self.dir = tempfile.mkdtemp(prefix="cachy-pads-")
        self.steam = FakeSteam(controllers, ps_support)

    def env(self, **extra):
        env = dict(os.environ)
        env["CACHY_CONSOLE_CDP_PORT"] = str(self.steam.port)
        env["XDG_STATE_HOME"] = self.dir
        env["CACHY_CONSOLE_PADS_RECONNECT"] = "1"
        env["CACHY_CONSOLE_GAMESCOPE_COMM"] = "cachy-test-no-such-comm"
        env.update(extra)
        return env

    @property
    def saved_path(self):
        return os.path.join(self.dir, "cachy-console", "ps-support-saved")

    def saved(self):
        try:
            with open(self.saved_path) as fh:
                return fh.read().strip()
        except OSError:
            return None

    def watch(self, primary="steam", **extra):
        return subprocess.Popen([TARGET, "watch", "--primary", primary,
                                 "--wait", "5", "--interval", "0.1"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, env=self.env(**extra))

    def settle(self, until, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if until():
                return True
            time.sleep(0.05)
        return False

    def clean(self):
        try:
            self.steam.stop()
        except OSError:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)


def finish(proc):
    proc.terminate()
    try:
        return proc.communicate(timeout=5)[0]
    except subprocess.TimeoutExpired:
        proc.kill()
        return proc.communicate()[0]


print("Who counts as what")
check("the Steam Controller is Steam hardware",
      pads.is_kind(pad(STEAM_CONTROLLER, 0), "steam"), True)
check("a DualSense is a PlayStation controller",
      pads.is_kind(pad(DUALSENSE, 0), "playstation"), True)
check("and not an Xbox one", pads.is_kind(pad(DUALSENSE, 0), "xbox"), False)
check("an XInput-mode DualSense is still found by its name",
      pads.is_kind({"type": 30, "name": "DualSense (XInput)", "slot": 0}, "playstation"), True)
check("unknown settings are refused rather than guessed",
      (pads.normalize("DualSense"), pads.normalize(" Steam ")), ("", "steam"))

print()
print("Which swap puts the chosen one first")
check("DualSense in player one and the Steam Controller second: swap them",
      pads.swap_needed([pad(DUALSENSE, 0), pad(STEAM_CONTROLLER, 1)], "steam"), (1, 0))
check("already first: nothing to do",
      pads.swap_needed([pad(STEAM_CONTROLLER, 0), pad(DUALSENSE, 1)], "steam"), None)
check("a controller outside Steam Input has no slot to move",
      pads.swap_needed([pad(DUALSENSE, 0), pad(STEAM_CONTROLLER, -1)], "steam"), None)
check("none of the chosen kind connected: nothing to do",
      pads.swap_needed([pad(DUALSENSE, 0), pad(XBOX, 1)], "steam"), None)
check("the other way round works too",
      pads.swap_needed([pad(STEAM_CONTROLLER, 0), pad(DUALSENSE, 1)], "playstation"), (1, 0))
check("the setting message is field 14003 as a varint",
      base64.b64decode(pads.ps_support_message(2)), bytes([0x98, 0xEB, 0x06, 0x02]))

print()
print("The watch, against a stand-in Steam")
w = World([pad(DUALSENSE, 0), pad(STEAM_CONTROLLER, 1)])
proc = w.watch()
moved = w.settle(lambda: w.steam.swaps)
check("the DualSense was player one; the Steam Controller is moved there",
      w.steam.swaps[:1], [(1, 0)])
check("PlayStation controllers are put through Steam Input for the session",
      w.steam.ps_support, 2)
check("and the setting the user had is written down", w.saved(), "1")
# The user moves them back by hand in the Quick Access menu.
w.steam.evaluate("SteamClient.Input.SwapControllerOrder(0,1)")
time.sleep(0.6)
check("a reorder made by hand afterwards is left alone", len(w.steam.swaps), 2)
# A third controller turning up is a new arrangement, decided again.
with w.steam.lock:
    w.steam.controllers.append(pad(XBOX, 2))
w.settle(lambda: len(w.steam.swaps) > 2)
check("but a controller connecting is, and the Steam Controller is first again",
      [c["slot"] for c in w.steam.controllers if c["index"] == 1], [0])
out = finish(proc)
check("what it did is said", "to player one" in out, True)
w.clean()

w = World([pad(DUALSENSE, 0), pad(STEAM_CONTROLLER, 1)])
proc = w.watch()
w.settle(lambda: w.steam.swaps)
w.steam.stop()
try:
    code = proc.wait(timeout=10)
except subprocess.TimeoutExpired:
    proc.kill()
    code = None
check("when Steam goes away, the watch ends by itself", code, 0)
w.clean()

w = World([pad(STEAM_CONTROLLER, 0), pad(DUALSENSE, 1)], ps_support=2)
proc = w.watch()
time.sleep(0.8)
finish(proc)
check("already in order: nothing is swapped", w.steam.swaps, [])
check("with PlayStation Steam Input already always on, nothing is written down",
      w.saved(), None)
w.clean()

w = World([pad(DUALSENSE, 0), pad(STEAM_CONTROLLER, 1)], ps_support=2)
os.makedirs(os.path.dirname(w.saved_path))
with open(w.saved_path, "w") as fh:
    fh.write("0\n")
proc = w.watch()
w.settle(lambda: w.steam.swaps)
finish(proc)
check("a value left by an earlier session is kept, not replaced by ours",
      w.saved(), "0")
w.clean()

w = World([pad(DUALSENSE, 0), pad(STEAM_CONTROLLER, 1)])
res = subprocess.run([TARGET, "watch", "--primary", "off"], capture_output=True,
                     text=True, timeout=10, env=w.env())
check("off does nothing at all", (res.returncode, w.steam.swaps, w.steam.ps_support),
      (0, [], 1))
res = subprocess.run([TARGET, "watch", "--primary", "dualsense"], capture_output=True,
                     text=True, timeout=10, env=w.env())
check("an unknown choice is refused, with the ones there are",
      (res.returncode, "playstation" in res.stdout), (2, True))
w.clean()

print()
print("Putting the setting back")
w = World([pad(STEAM_CONTROLLER, 0)], ps_support=2)
os.makedirs(os.path.dirname(w.saved_path))
with open(w.saved_path, "w") as fh:
    fh.write("1\n")
res = subprocess.run([TARGET, "restore", "--wait", "10"], capture_output=True,
                     text=True, timeout=30, env=w.env())
check("the desktop client gets the user's setting back", w.steam.ps_support, 1)
check("and the note is cleared once it has taken", w.saved(), None)
w.clean()

w = World([pad(STEAM_CONTROLLER, 0)], ps_support=2)
res = subprocess.run([TARGET, "restore", "--wait", "3"], capture_output=True,
                     text=True, timeout=30, env=w.env())
check("with nothing written down, nothing is changed",
      (res.returncode, w.steam.ps_support), (0, 2))
w.clean()

# A console session still up: its client is the one answering, and the
# setting it needs must not be taken away from under it.
w = World([pad(STEAM_CONTROLLER, 0)], ps_support=2)
os.makedirs(os.path.dirname(w.saved_path))
with open(w.saved_path, "w") as fh:
    fh.write("1\n")
gs_bin = os.path.join(w.dir, "cachy-fake-gs")
shutil.copy("/bin/sleep", gs_bin)
fake_gs = subprocess.Popen([gs_bin, "30"])
res = subprocess.run([TARGET, "restore", "--wait", "3"], capture_output=True,
                     text=True, timeout=30,
                     env=w.env(CACHY_CONSOLE_GAMESCOPE_COMM="cachy-fake-gs"))
check("while console mode is running, the session's client is left alone",
      (w.steam.ps_support, w.saved()), (2, "1"))
fake_gs.kill()
fake_gs.wait()
w.clean()

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
    sys.exit(1)
print("all player-one tests passed")
