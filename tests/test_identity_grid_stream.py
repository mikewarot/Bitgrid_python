from __future__ import annotations

import socket, subprocess, sys, tempfile, time, unittest
from typing import Dict, Tuple, List

from bitgrid.cli.make_identity_program import build_identity_program
from bitgrid.protocol import (
    pack_frame, try_parse_frame, MsgType,
    encode_name_u64_map, decode_name_u64_map,
    payload_hello,
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


class TestIdentityGridStream(unittest.TestCase):
    def test_identity_9bit_stream(self):
        with tempfile.TemporaryDirectory() as td:
            prog = build_identity_program(16, 10, lanes=9, row0=0)
            pth = td + '/identity_program.json'
            prog.save(pth)

            port = _free_port()
            proc = subprocess.Popen([sys.executable, '-m', 'bitgrid.cli.serve_tcp', '--program', pth, '--host', '127.0.0.1', '--port', str(port)])
            try:
                # Wait for server
                t0 = time.time(); ok = False
                while time.time() - t0 < 5.0 and not ok:
                    try:
                        with _connect('127.0.0.1', port) as s:
                            w, h = _hello(s)
                            ok = (w > 0 and h > 0)
                    except Exception:
                        time.sleep(0.05)
                self.assertTrue(ok, 'Server did not respond to HELLO')

                # Control socket
                s = _connect('127.0.0.1', port)
                try:
                    # Send 9-bit framed bytes over west: lower 8 bits = data, bit8 = present flag
                    cps = 1  # subcycle-level control (not critical with zero-latency IO)
                    message = 'Hello, World, this is a much longer test than before'
                    width = len(message)+3
                    out: List[int] = []
                    for ch in message:
                        # Assert present+data, then read it, then clear
                        frame = (1 << 8) | (ord(ch) & 0xFF)
                        _set_inputs(s, {'west': frame})
                        # Optionally advance a subcycle
                        _step(s, cps)
                        # Poll for present=1
                        captured = False
                        deadline = time.time() + 1.0
                        while time.time() < deadline:
                            m = _get_outputs(s)
                            east = int(m.get('east', 0))
                            present = (east >> 8) & 1
                            data = east & 0xFF
                            if present == 1:
                                out.append(data)
                                captured = True
                                break
                            time.sleep(0.005)
                        self.assertTrue(captured, 'Did not observe present flag at east in time')
                        # Clear present and advance
                        _set_inputs(s, {'west': 0})
                        _step(s, cps)
                    text = ''.join(chr(b) for b in out[:len(message)])
                    self.assertEqual(text, message)
                finally:
                    try:
                        s.sendall(pack_frame(MsgType.SHUTDOWN))
                    except Exception:
                        pass
                    s.close()
            finally:
                try:
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.terminate(); proc.wait(timeout=2)
                    except Exception:
                        proc.kill()


if __name__ == '__main__':
    unittest.main()
