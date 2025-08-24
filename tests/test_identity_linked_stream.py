from __future__ import annotations

import os, socket, subprocess, sys, tempfile, time, unittest
from typing import Dict, Tuple, List

from bitgrid.cli.make_identity_program import build_identity_program
from bitgrid.protocol import (
    pack_frame, try_parse_frame, MsgType,
    encode_name_u64_map, decode_name_u64_map,
    payload_hello, payload_link,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _connect(host: str, port: int, timeout: float = 3.0) -> socket.socket:
    return socket.create_connection((host, port), timeout=timeout)


def _send_and_recv(sock: socket.socket, frame: bytes, timeout: float = 3.0):
    sock.sendall(frame)
    sock.settimeout(timeout)
    buf = b''
    end = time.time() + timeout
    while time.time() < end:
        frame_parsed, buf = try_parse_frame(buf)
        if frame_parsed is not None:
            return frame_parsed
        try:
            data = sock.recv(4096)
        except socket.timeout:
            break
        if not data:
            break
        buf += data
    return None


def _hello(sock: socket.socket) -> Tuple[int, int]:
    resp = _send_and_recv(sock, pack_frame(MsgType.HELLO, payload_hello(0, 0)))
    if not resp or resp.get('type') != MsgType.HELLO:
        return 0, 0
    import struct
    payload = resp.get('payload', b'')
    if len(payload) < 10:
        return 0, 0
    width, height, _pv, _feat = struct.unpack('<HHHI', payload[:10])
    return width, height


def _set_inputs(sock: socket.socket, kv: Dict[str, int]) -> None:
    sock.sendall(pack_frame(MsgType.SET_INPUTS, encode_name_u64_map(kv)))


def _step(sock: socket.socket, cycles: int = 1) -> None:
    import struct
    sock.sendall(pack_frame(MsgType.STEP, struct.pack('<I', int(cycles) & 0xFFFFFFFF)))


def _get_outputs(sock: socket.socket, timeout: float = 3.0) -> Dict[str, int]:
    sock.sendall(pack_frame(MsgType.GET_OUTPUTS))
    resp = _send_and_recv(sock, b'', timeout=timeout)
    if not resp or resp.get('type') != MsgType.OUTPUTS:
        return {}
    m, _ = decode_name_u64_map(resp['payload'])
    return m


class TestIdentityLinkedStream(unittest.TestCase):
    def test_identity_9bit_linked(self):
        with tempfile.TemporaryDirectory() as td:
            prog = build_identity_program(16, 10, lanes=9, row0=0)
            lp = _free_port(); rp = _free_port()
            left_path = td + '/left.json'; right_path = td + '/right.json'
            prog.save(left_path); prog.save(right_path)

            left_proc = subprocess.Popen([sys.executable, '-m', 'bitgrid.cli.serve_tcp', '--program', left_path, '--host', '127.0.0.1', '--port', str(lp)])
            right_proc = subprocess.Popen([sys.executable, '-m', 'bitgrid.cli.serve_tcp', '--program', right_path, '--host', '127.0.0.1', '--port', str(rp)])
            try:
                # Wait for servers
                wait_server = float(os.environ.get('BG_TEST_WAIT_SERVER', '10.0'))
                t0 = time.time(); left_ok = right_ok = False
                while time.time() - t0 < wait_server and not (left_ok and right_ok):
                    try:
                        with _connect('127.0.0.1', lp) as s:
                            w, h = _hello(s); left_ok = (w > 0 and h > 0)
                    except Exception:
                        time.sleep(0.05)
                    try:
                        with _connect('127.0.0.1', rp) as s:
                            w, h = _hello(s); right_ok = (w > 0 and h > 0)
                    except Exception:
                        time.sleep(0.05)
                self.assertTrue(left_ok and right_ok, 'Servers did not respond to HELLO')

                left = _connect('127.0.0.1', lp)
                right = _connect('127.0.0.1', rp)
                try:
                    # Link left.east -> right.west (lanes auto)
                    payload = payload_link(1, 'east', 'west', '127.0.0.1', rp, lanes=0)
                    left.sendall(pack_frame(MsgType.LINK, payload))
                    resp = _send_and_recv(left, b'', timeout=3.0)
                    if not resp or resp.get('type') != MsgType.LINK_ACK:
                        self.fail('No LINK_ACK from left during setup')

                    cps = 2
                    wait_present = float(os.environ.get('BG_TEST_WAIT_PRESENT', '3.0'))
                    wait_clear = float(os.environ.get('BG_TEST_WAIT_CLEAR', '3.0'))
                    message = 'Hello, World! Hello, Linked Grid!'
                    out: List[int] = []
                    for ch in message:
                        # Send data+present
                        frame = (1 << 8) | (ord(ch) & 0xFF)
                        _set_inputs(left, {'west': frame})
                        _step(left, cps)  # delivers one value on B-phase
                        # Wait until right shows present=1 and capture
                        deadline = time.time() + wait_present
                        captured = False
                        while time.time() < deadline:
                            m = _get_outputs(right, timeout=0.5)
                            east = int(m.get('east', 0))
                            present = (east >> 8) & 1
                            data = east & 0xFF
                            if present == 1:
                                out.append(data)
                                captured = True
                                break
                            time.sleep(0.005)
                        self.assertTrue(captured, 'No present observed at receiver in time')
                        # Clear on next cycle so receiver can see present drop
                        _set_inputs(left, {'west': 0})
                        _step(left, cps)
                        # Wait for present to drop to 0 before next char
                        deadline2 = time.time() + wait_clear
                        while time.time() < deadline2:
                            m2 = _get_outputs(right, timeout=0.5)
                            east2 = int(m2.get('east', 0))
                            present2 = (east2 >> 8) & 1
                            if present2 == 0:
                                break
                            time.sleep(0.005)

                    text = ''.join(chr(b) for b in out[:len(message)])
                    self.assertEqual(text, message)
                finally:
                    try:
                        left.sendall(pack_frame(MsgType.UNLINK))
                    except Exception:
                        pass
                    try:
                        left.sendall(pack_frame(MsgType.SHUTDOWN))
                    except Exception:
                        pass
                    try:
                        right.sendall(pack_frame(MsgType.SHUTDOWN))
                    except Exception:
                        pass
                    left.close(); right.close()
            finally:
                for p in (left_proc, right_proc):
                    try:
                        p.wait(timeout=3)
                    except Exception:
                        try:
                            p.terminate(); p.wait(timeout=2)
                        except Exception:
                            p.kill()


if __name__ == '__main__':
    unittest.main()
