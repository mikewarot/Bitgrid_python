from __future__ import annotations

import argparse
import socket
import struct
from typing import Dict, Tuple, List

from ..protocol import (
    pack_frame,
    try_parse_frame,
    MsgType,
    encode_name_u64_map,
    decode_name_u64_map,
    payload_hello,
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
    payload = resp.get('payload', b'')
    if len(payload) < 10:
        return 0, 0
    width, height, _pv, _feat = struct.unpack('<HHHI', payload[:10])
    return width, height


def _set_inputs(sock: socket.socket, kv: Dict[str, int]) -> None:
    sock.sendall(pack_frame(MsgType.SET_INPUTS, encode_name_u64_map(kv)))


def _step(sock: socket.socket, cycles: int = 1) -> None:
    sock.sendall(pack_frame(MsgType.STEP, struct.pack('<I', int(cycles) & 0xFFFFFFFF)))


def _get_outputs(sock: socket.socket, timeout: float = 2.0) -> Dict[str, int]:
    sock.sendall(pack_frame(MsgType.GET_OUTPUTS))
    resp = _send_and_recv(sock, b'', timeout=timeout)
    if not resp or resp.get('type') != MsgType.OUTPUTS:
        return {}
    m, _ = decode_name_u64_map(resp['payload'])
    return m


def pack_bits(bits: List[int]) -> int:
    v = 0
    for i, b in enumerate(bits):
        v |= (int(b) & 1) << i
    return v


def unpack_bits(val: int, n: int) -> List[int]:
    return [((int(val) >> i) & 1) for i in range(n)]


def east_fresh_indices(width: int, height: int, phase: str) -> List[int]:
    # East edge is at x=width-1; when width is even, x is odd -> A: odd y, B: even y
    # When width is odd, x is even -> A: even y, B: odd y
    x_east = width - 1
    if phase == 'A':
        return [y for y in range(height) if ((x_east + y) % 2 == 0)]
    else:
        return [y for y in range(height) if ((x_east + y) % 2 == 1)]


def main():
    ap = argparse.ArgumentParser(description='Bridge two BGCF emulator servers over a single west<->east seam (left.east -> right.west).')
    ap.add_argument('--left', default='127.0.0.1:9000', help='Left server host:port (source east edge)')
    ap.add_argument('--right', default='127.0.0.1:9002', help='Right server host:port (sink west edge)')
    ap.add_argument('--epochs', type=int, default=8, help='Number of epochs to run (each epoch = A then B)')
    ap.add_argument('--left-east-name', default='east', help='Left server output name for east edge')
    ap.add_argument('--right-west-name', default='west', help='Right server input name for west edge')
    ap.add_argument('--timeout', type=float, default=2.0, help='Socket timeout seconds for replies')
    args = ap.parse_args()

    lh, lp = args.left.split(':', 1)
    rh, rp = args.right.split(':', 1)
    lp = int(lp); rp = int(rp)

    with _connect(lh, lp) as left, _connect(rh, rp) as right:
        lw, lhgt = _hello(left)
        rw, rhgt = _hello(right)
        if lw == 0 or lhgt == 0 or rhgt == 0:
            print('HELLO failed (dims unknown).')
            return 2
        lanes = min(lhgt, rhgt)
        print(f'left: {lw}x{lhgt}; right: {rw}x{rhgt}; lanes={lanes}')

        # Receiver buffers split by parity
        buf_even = [0] * lanes
        buf_odd = [0] * lanes

        # Precompute fresh indices for left east edge
        idxA = [i for i in east_fresh_indices(lw, lanes, 'A') if i < lanes]
        idxB = [i for i in east_fresh_indices(lw, lanes, 'B') if i < lanes]
        even_mask = sum(1 << i for i in range(lanes) if (i % 2 == 0))
        odd_mask = sum(1 << i for i in range(lanes) if (i % 2 == 1))

        for epoch in range(args.epochs):
            # Phase A: right consumes even buffer; left produces odd lanes
            _set_inputs(right, {args.right_west_name: pack_bits(buf_even)})
            _step(left, 1)
            _step(right, 1)
            outsA = _get_outputs(left, timeout=args.timeout)
            leA = outsA.get(args.left_east_name, 0)
            eastA = unpack_bits(leA, lanes)
            for i in idxA:  # fresh at A
                buf_odd[i] = eastA[i] & 1

            # Phase B: right consumes odd buffer; left produces even lanes
            _set_inputs(right, {args.right_west_name: pack_bits(buf_odd)})
            _step(left, 1)
            _step(right, 1)
            outsB = _get_outputs(left, timeout=args.timeout)
            leB = outsB.get(args.left_east_name, 0)
            eastB = unpack_bits(leB, lanes)
            for i in idxB:  # fresh at B
                buf_even[i] = eastB[i] & 1

            # Report aligned vector available for epoch-1
            if epoch - 1 >= 0:
                aligned = (pack_bits(buf_odd) & odd_mask) | (pack_bits(buf_even) & even_mask)
                print(f'epoch={epoch} A_even=0x{(pack_bits(buf_even) & even_mask):0{(lanes+3)//4}X} B_odd=0x{(pack_bits(buf_odd) & odd_mask):0{(lanes+3)//4}X} aligned[e-1]=0x{aligned:0{(lanes+3)//4}X}')
            else:
                print(f'epoch={epoch} A_even=0x{(pack_bits(buf_even) & even_mask):0{(lanes+3)//4}X} B_odd=0x{(pack_bits(buf_odd) & odd_mask):0{(lanes+3)//4}X}')


if __name__ == '__main__':
    main()
