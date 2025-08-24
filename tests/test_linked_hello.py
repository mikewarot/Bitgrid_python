from __future__ import annotations

import os, socket
import subprocess
import sys
import tempfile
import time
import unittest
from typing import Dict, Tuple, List

from bitgrid.cli.make_edge_programs import (
    build_left_program_edge_io,
    build_right_program_edge_io,
)
from bitgrid.protocol import (
    pack_frame,
    try_parse_frame,
    MsgType,
    encode_name_u64_map,
    decode_name_u64_map,
    payload_hello,
    payload_link,
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


class TestLinkedHello(unittest.TestCase):
    def test_linked_hello(self):
        # Build simple left/right programs
        with tempfile.TemporaryDirectory() as td:
            left_prog = build_left_program_edge_io(16, 8, 8)
            right_prog = build_right_program_edge_io(16, 8, 8)
            left_path = td + '/left_program.json'
            right_path = td + '/right_program.json'
            left_prog.save(left_path)
            right_prog.save(right_path)

            # Free ports
            lp = _free_port()
            rp = _free_port()

            # Start servers (quiet)
            left_proc = subprocess.Popen([sys.executable, '-m', 'bitgrid.cli.serve_tcp', '--program', left_path, '--host', '127.0.0.1', '--port', str(lp)])
            right_proc = subprocess.Popen([sys.executable, '-m', 'bitgrid.cli.serve_tcp', '--program', right_path, '--host', '127.0.0.1', '--port', str(rp)])
            try:
                # Wait for HELLO to succeed
                wait_server = float(os.environ.get('BG_TEST_WAIT_SERVER', '10.0'))
                t0 = time.time()
                left_ok = right_ok = False
                while time.time() - t0 < wait_server and not (left_ok and right_ok):
                    try:
                        with _connect('127.0.0.1', lp) as s:
                            w, h = _hello(s)
                            left_ok = (w > 0 and h > 0)
                    except Exception:
                        time.sleep(0.05)
                    try:
                        with _connect('127.0.0.1', rp) as s:
                            w, h = _hello(s)
                            right_ok = (w > 0 and h > 0)
                    except Exception:
                        time.sleep(0.05)
                self.assertTrue(left_ok and right_ok, 'Servers did not respond to HELLO')

                # Open control sockets
                left = _connect('127.0.0.1', lp)
                right = _connect('127.0.0.1', rp)
                try:
                    # Request link east->west
                    payload = payload_link(1, 'east', 'west', '127.0.0.1', rp, lanes=0)
                    left.sendall(pack_frame(MsgType.LINK, payload))
                    # Expect LINK_ACK or ERROR
                    resp = _send_and_recv(left, b'', timeout=3.0)
                    self.assertIsNotNone(resp, 'No response to LINK')
                    rtype = resp['type']  # type: ignore[index]
                    self.assertIn(rtype, (MsgType.LINK_ACK, MsgType.ERROR))
                    self.assertEqual(rtype, MsgType.LINK_ACK, f'LINK failed: {resp}')

                    # Run multiple message cases with dynamic flush window and cps
                    cases: List[Tuple[str, int]] = [
                        ("", 2),
                        ("Hello!", 2),
                        ("Heeellloooo!!", 2),
                        ("Hello, World!", 2),
                    ]

                    wait_present = float(os.environ.get('BG_TEST_WAIT_PRESENT', '3.0'))
                    wait_clear = float(os.environ.get('BG_TEST_WAIT_CLEAR', '3.0'))
                    for message, cps in cases:
                        with self.subTest(message=message, cps=cps):
                            # Send message characters and sample outputs per character
                            need = len(message)
                            out_bytes: List[int] = []
                            prev = None
                            for ch in message:
                                _set_inputs(left, {'west': ord(ch) & 0xFF})
                                _step(left, cps)
                                # Wait until a new non-zero byte appears (or timeout)
                                target_len = len(out_bytes) + 1
                                deadline = time.time() + wait_present
                                while time.time() < deadline:
                                    m = _get_outputs(right, timeout=0.5)
                                    b = int(m.get('east', 0)) & 0xFF
                                    if b != 0:
                                        out_bytes.append(b)
                                        break
                                    time.sleep(0.005)
                                # small clear step between chars to avoid coalescing
                                _set_inputs(left, {'west': 0})
                                _step(left, cps)
                                # wait for zero to be seen (optional)
                                deadline2 = time.time() + wait_clear
                                while time.time() < deadline2:
                                    m2 = _get_outputs(right, timeout=0.5)
                                    if (int(m2.get('east', 0)) & 0xFF) == 0:
                                        break
                                    time.sleep(0.005)
                            # Briefly clear to zero at the end
                            for _ in range(2):
                                _set_inputs(left, {'west': 0})
                                _step(left, cps)
                            text_out = ''.join(chr(b) for b in out_bytes[:need])
                            self.assertEqual(text_out, message)
                            # Drain a bit more with zeros to avoid cross-case leftovers
                            for _ in range(4):
                                _set_inputs(left, {'west': 0})
                                _step(left, cps)
                finally:
                    # Teardown
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
                # Ensure processes exit
                for p in (left_proc, right_proc):
                    try:
                        p.wait(timeout=3)
                    except Exception:
                        try:
                            p.terminate()
                            p.wait(timeout=2)
                        except Exception:
                            p.kill()


if __name__ == '__main__':
    unittest.main()
