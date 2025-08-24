from __future__ import annotations

import os, socket, subprocess, sys, tempfile, time, unittest
from typing import Dict, Tuple, List

from bitgrid.cli.make_identity_program import build_identity_program_4way, build_edge_mirror
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


class TestLinkedDirections(unittest.TestCase):
    def _run_dir(self, dir_code: int, local_edge: str, remote_edge: str):
        """Start two servers, link local_edge(out)->remote_edge(in) by dir, and stream a short message using present+data on the local edge input."""
        with tempfile.TemporaryDirectory() as td:
            lp = _free_port(); rp = _free_port()
            # Mirror on same-named edges: left outputs local_edge, right latches remote_edge
            left_prog = build_edge_mirror(16, 10, local_edge, lanes=9)
            right_prog = build_edge_mirror(16, 10, remote_edge, lanes=9)
            left_path = td + '/left.json'; right_path = td + '/right.json'
            left_prog.save(left_path); right_prog.save(right_path)

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
                    # Link left(src) -> right(dst)
                    payload = payload_link(dir_code, local_edge, remote_edge, '127.0.0.1', rp, lanes=0)
                    left.sendall(pack_frame(MsgType.LINK, payload))
                    resp = _send_and_recv(left, b'', timeout=3.0)
                    if not resp or resp.get('type') != MsgType.LINK_ACK:
                        self.fail('No LINK_ACK from left')

                    cps = 2
                    message = 'NSWE test!'
                    wait_present = float(os.environ.get('BG_TEST_WAIT_PRESENT', '3.0'))
                    wait_clear = float(os.environ.get('BG_TEST_WAIT_CLEAR', '3.0'))
                    out: List[int] = []
                    for ch in message:
                        frame = (1 << 8) | (ord(ch) & 0xFF)
                        _set_inputs(left, {local_edge: frame})
                        _step(left, cps)
                        # Poll right on dst
                        deadline = time.time() + wait_present
                        captured = False
                        while time.time() < deadline:
                            m = _get_outputs(right, timeout=0.5)
                            seam = int(m.get(remote_edge, 0))
                            present = (seam >> 8) & 1
                            data = seam & 0xFF
                            if present == 1:
                                out.append(data)
                                captured = True
                                break
                            time.sleep(0.005)
                        self.assertTrue(captured, 'No present observed at receiver in time')
                        _set_inputs(left, {local_edge: 0})
                        _step(left, cps)
                        # Wait for present to drop
                        deadline2 = time.time() + wait_clear
                        while time.time() < deadline2:
                            m2 = _get_outputs(right, timeout=0.5)
                            if ((int(m2.get(remote_edge, 0)) >> 8) & 1) == 0:
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

    def test_north(self):
        # north seam: left local_out='north' -> right remote_in='south'
        self._run_dir(0, 'north', 'south')

    def test_west(self):
        # west seam: left local_out='west' -> right remote_in='east'
        self._run_dir(3, 'west', 'east')

    def test_south(self):
        # south seam: left local_out='south' -> right remote_in='north'
        self._run_dir(2, 'south', 'north')


class TestLinkedFourWay(unittest.TestCase):
    def test_four_way_simultaneous(self):
        with tempfile.TemporaryDirectory() as td:
            lp = _free_port(); rp = _free_port()
            left_prog = build_identity_program_4way(16, 10, lanes=9)
            right_prog = build_identity_program_4way(16, 10, lanes=9)
            left_path = td + '/left4.json'; right_path = td + '/right4.json'
            left_prog.save(left_path); right_prog.save(right_path)

            left_proc = subprocess.Popen([sys.executable, '-m', 'bitgrid.cli.serve_tcp', '--program', left_path, '--host', '127.0.0.1', '--port', str(lp)])
            right_proc = subprocess.Popen([sys.executable, '-m', 'bitgrid.cli.serve_tcp', '--program', right_path, '--host', '127.0.0.1', '--port', str(rp)])
            try:
                # Wait for servers
                t0 = time.time(); left_ok = right_ok = False
                while time.time() - t0 < 5.0 and not (left_ok and right_ok):
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
                    # Establish links for all four directions
                    links = [
                        (1, 'east', 'west'),
                        (3, 'west', 'east'),
                        (0, 'north', 'south'),
                        (2, 'south', 'north'),
                    ]
                    for code, lo, ri in links:
                        left.sendall(pack_frame(MsgType.LINK, payload_link(code, lo, ri, '127.0.0.1', rp, lanes=0)))
                        resp = _send_and_recv(left, b'', timeout=3.0)
                        if resp is None:
                            self.fail('No LINK_ACK during 4-way setup')
                        self.assertEqual(resp.get('type'), MsgType.LINK_ACK)

                    cps = 2
                    msgs = {
                        'west':  'W->E',
                        'east':  'E->W',
                        'north': 'N->S',
                        'south': 'S->N',
                    }
                    outs = { 'east': [], 'west': [], 'south': [], 'north': [] }
                    max_len = max(len(v) for v in msgs.values())
                    for i in range(max_len):
                        # Drive present+data on all sources that have remaining chars
                        for src, text in msgs.items():
                            if i < len(text):
                                _set_inputs(left, {src: (1<<8) | (ord(text[i]) & 0xFF)})
                        _step(left, cps)
                        # Poll all four destinations on right
                        deadline = time.time() + 1.0
                        got = { 'east': True, 'west': True, 'south': True, 'north': True }
                        for src, text in msgs.items():
                            if i < len(text):
                                # Determine destination bus for this src
                                dst = 'east' if src == 'west' else 'west' if src == 'east' else 'south' if src == 'north' else 'north'
                                got[dst] = False
                        while time.time() < deadline and not all(got.values()):
                            m = _get_outputs(right, timeout=0.5)
                            for dst in list(got.keys()):
                                if got[dst]:
                                    continue
                                seam = int(m.get(dst, 0))
                                if ((seam >> 8) & 1) == 1:
                                    outs[dst].append(seam & 0xFF)
                                    got[dst] = True
                            if not all(got.values()):
                                time.sleep(0.005)
                        # Clear all asserted sources
                        for src, text in msgs.items():
                            if i < len(text):
                                _set_inputs(left, {src: 0})
                        _step(left, cps)
                        # Wait for present to drop on all dsts
                        deadline2 = time.time() + 1.0
                        while time.time() < deadline2:
                            m2 = _get_outputs(right, timeout=0.5)
                            ok = True
                            for src, text in msgs.items():
                                if i < len(text):
                                    dst = 'east' if src == 'west' else 'west' if src == 'east' else 'south' if src == 'north' else 'north'
                                    if ((int(m2.get(dst, 0)) >> 8) & 1) == 1:
                                        ok = False
                                        break
                            if ok:
                                break
                            time.sleep(0.005)
                    # Validate received strings
                    self.assertEqual(''.join(map(chr, outs['east'])), msgs['west'])
                    self.assertEqual(''.join(map(chr, outs['west'])), msgs['east'])
                    self.assertEqual(''.join(map(chr, outs['south'])), msgs['north'])
                    self.assertEqual(''.join(map(chr, outs['north'])), msgs['south'])
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
