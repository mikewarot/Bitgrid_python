from __future__ import annotations

import os, socket, subprocess, sys, tempfile, time, unittest
from typing import Dict, Tuple, List

from bitgrid.cli.make_identity_program import build_inout_program
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


class TestIdentityLinkedDuplex(unittest.TestCase):
    def test_identity_9bit_linked_duplex(self):
        with tempfile.TemporaryDirectory() as td:
            prog = build_inout_program(16, 10, lanes=9)
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
                    # Establish links in both directions
                    # Left -> Right: left.east_out -> right.west_in (drive left 'west_in', observe on right 'east_in')
                    payload_lr = payload_link(1, 'east_out', 'west_in', '127.0.0.1', rp, lanes=0)
                    left.sendall(pack_frame(MsgType.LINK, payload_lr))
                    resp1 = _send_and_recv(left, b'', timeout=3.0)
                    if not resp1 or resp1.get('type') != MsgType.LINK_ACK:
                        self.fail('No LINK_ACK from left for left->right link')

                    # Right -> Left: right.west_out -> left.east_in (drive right 'east_in', observe on left 'west_in')
                    payload_rl = payload_link(3, 'west_out', 'east_in', '127.0.0.1', lp, lanes=0)
                    right.sendall(pack_frame(MsgType.LINK, payload_rl))
                    resp2 = _send_and_recv(right, b'', timeout=3.0)
                    if not resp2 or resp2.get('type') != MsgType.LINK_ACK:
                        self.fail('No LINK_ACK from right for right->left link')

                    cps = 2
                    msgL = 'Left->Right stream!'  # from left to right
                    msgR = 'Right->Left reply.'  # from right to left
                    wait_present = float(os.environ.get('BG_TEST_WAIT_PRESENT', '3.0'))
                    wait_clear = float(os.environ.get('BG_TEST_WAIT_CLEAR', '3.0'))
                    outR: List[int] = []  # what right receives (from left)
                    outL: List[int] = []  # what left receives (from right)

                    max_len = max(len(msgL), len(msgR))
                    for i in range(max_len):
                        # Drive inputs for this symbol on both ends (if any remain)
                        if i < len(msgL):
                            frameL = (1 << 8) | (ord(msgL[i]) & 0xFF)
                            _set_inputs(left, {'west_in': frameL})
                        if i < len(msgR):
                            frameR = (1 << 8) | (ord(msgR[i]) & 0xFF)
                            _set_inputs(right, {'east_in': frameR})
                        # Step both ends so each owner forwards its link direction
                        _step(left, cps)
                        _step(right, cps)
                        # Poll receivers on both ends
                        deadline = time.time() + wait_present
                        gotR = (i >= len(msgL))  # if no symbol sent, treat as trivially satisfied
                        gotL = (i >= len(msgR))
                        while time.time() < deadline and not (gotR and gotL):
                            if not gotR:
                                mR = _get_outputs(right, timeout=0.5)
                                eastR = int(mR.get('east_in', 0))
                                if ((eastR >> 8) & 1) == 1:
                                    outR.append(eastR & 0xFF)
                                    gotR = True
                            if not gotL:
                                mL = _get_outputs(left, timeout=0.5)
                                westL = int(mL.get('west_in', 0))
                                if ((westL >> 8) & 1) == 1:
                                    outL.append(westL & 0xFF)
                                    gotL = True
                            if not (gotR and gotL):
                                time.sleep(0.005)
                        self.assertTrue(gotR and gotL, 'Did not observe present on one or both ends in time')
                        # Clear both ends for next symbol
                        if i < len(msgL):
                            _set_inputs(left, {'west_in': 0})
                        if i < len(msgR):
                            _set_inputs(right, {'east_in': 0})
                        _step(left, cps)
                        _step(right, cps)
                        # Wait for present to drop on both ends
                        deadline2 = time.time() + wait_clear
                        while time.time() < deadline2:
                            okR = True if i >= len(msgL) else (((int(_get_outputs(right).get('east_in', 0)) >> 8) & 1) == 0)
                            okL = True if i >= len(msgR) else (((int(_get_outputs(left).get('west_in', 0)) >> 8) & 1) == 0)
                            if okR and okL:
                                break
                            time.sleep(0.005)

                    textR = ''.join(chr(b) for b in outR[:len(msgL)])
                    textL = ''.join(chr(b) for b in outL[:len(msgR)])
                    self.assertEqual(textR, msgL)
                    self.assertEqual(textL, msgR)
                finally:
                    try:
                        left.sendall(pack_frame(MsgType.UNLINK))
                    except Exception:
                        pass
                    try:
                        right.sendall(pack_frame(MsgType.UNLINK))
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
