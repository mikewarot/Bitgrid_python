from __future__ import annotations

import argparse
import socket
from typing import Dict, Tuple, List

from ..protocol import (
    pack_frame,
    try_parse_frame,
    MsgType,
    encode_name_u64_map,
    decode_name_u64_map,
    payload_hello,
    payload_link,
)


def _connect(host: str, port: int, timeout: float = 2.0) -> socket.socket:
    return socket.create_connection((host, port), timeout=timeout)


def _send_and_recv(sock: socket.socket, frame: bytes, timeout: float = 2.0):
    sock.sendall(frame)
    sock.settimeout(timeout)
    buf = b''
    while True:
        frame_parsed, buf = try_parse_frame(buf)
        if frame_parsed is not None:
            return frame_parsed
        try:
            data = sock.recv(4096)
        except socket.timeout:
            return None
        if not data:
            return None
        buf += data


def _hello(sock: socket.socket) -> Tuple[int, int]:
    # Request HELLO; server replies with HELLO carrying dims
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


def _get_outputs(sock: socket.socket, timeout: float = 2.0) -> Dict[str, int]:
    sock.sendall(pack_frame(MsgType.GET_OUTPUTS))
    resp = _send_and_recv(sock, b'', timeout=timeout)
    if not resp or resp.get('type') != MsgType.OUTPUTS:
        return {}
    m, _ = decode_name_u64_map(resp['payload'])
    return m


def main():
    ap = argparse.ArgumentParser(description='Demo: send text through two linked servers (left: din -> east; right: west -> dout)')
    ap.add_argument('--left', default='127.0.0.1:9000', help='Left server host:port')
    ap.add_argument('--right', default='127.0.0.1:9002', help='Right server host:port')
    ap.add_argument('--text', default='Hello, World!')
    ap.add_argument('--left-east-name', default='east')
    ap.add_argument('--right-west-name', default='west')
    ap.add_argument('--right-out-name', default='dout')
    ap.add_argument('--cps', type=int, default=2, help='cycles per character (2 recommended)')
    ap.add_argument('--flush', type=int, default=14, help='extra zero-steps to flush pipeline')
    args = ap.parse_args()

    lh, lp = args.left.split(':', 1)
    rh, rp = args.right.split(':', 1)
    lp = int(lp); rp = int(rp)

    with _connect(lh, lp) as left, _connect(rh, rp) as right:
        lw, lhgt = _hello(left)
        rw, rhgt = _hello(right)
        if lw == 0 or lhgt == 0 or rw == 0 or rhgt == 0:
            print('HELLO failed')
            return 2

        # Ask LEFT to link to RIGHT (east -> west)
        payload = payload_link(1, args.left_east_name, args.right_west_name, rh, rp, lanes=0)
        left.sendall(pack_frame(MsgType.LINK, payload))

        cps = max(1, int(args.cps))
        message = args.text
        out_bytes: List[int] = []
        need = len(message)

        # Stream chars
        for ch in message:
            _set_inputs(left, {'din': ord(ch) & 0xFF})
            _step(left, cps)
            # Poll right output
            m = _get_outputs(right)
            b = int(m.get(args.right_out_name, 0)) & 0xFF
            if b != 0:
                out_bytes.append(b)
                if len(out_bytes) >= need:
                    break

        # Flush zeros
        for _ in range(args.flush):
            _set_inputs(left, {'din': 0})
            _step(left, cps)
            m = _get_outputs(right)
            b = int(m.get(args.right_out_name, 0)) & 0xFF
            if b != 0:
                out_bytes.append(b)
                if len(out_bytes) >= need:
                    break

        text_out = ''.join(chr(b) for b in out_bytes[:need])
        print(text_out)


if __name__ == '__main__':
    main()
