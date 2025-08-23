from __future__ import annotations

import argparse
import socket
from typing import Dict, Tuple
import threading
from ..program import Program
from ..emulator import Emulator
from ..protocol import (
    pack_frame,
    try_parse_frame,
    MsgType,
    encode_name_u64_map,
    decode_name_u64_map,
    payload_hello,
)


def _parse_load_chunk(payload: bytes) -> Tuple[int, int, int, bytes]:
    import struct
    if len(payload) < 2 + 4 + 4 + 2:
        raise ValueError('LOAD_CHUNK too short')
    session_id, total_bytes, offset, clen = struct.unpack('<HIIH', payload[:12])
    chunk = payload[12:12+clen]
    if len(chunk) != clen:
        raise ValueError('LOAD_CHUNK chunk length mismatch')
    return session_id, total_bytes, offset, chunk


def handle_client(conn: socket.socket, prog: Program, preloaded_bitstream: bytes | None = None, verbose: bool = True, shutdown_event: threading.Event | None = None) -> None:
    conn.settimeout(1.0)
    emu = Emulator(prog)
    current_inputs: Dict[str, int] = {name: 0 for name in prog.input_bits.keys()}
    # Sessions for assembling bitstreams
    sessions: Dict[int, Dict] = {}

    if preloaded_bitstream:
        try:
            meta = emu.load_bitstream(preloaded_bitstream)
            if verbose:
                print(f'[srv] preloaded bitstream: used_header={meta["used_header"]} order={meta["order"]} dims={meta["width"]}x{meta["height"]}')
        except Exception as e:
            if verbose:
                print(f'[srv] preload failed: {e}')

    buf = b''
    seq = 0
    peer = conn.getpeername()
    if verbose:
        print(f'[srv] connected: {peer}')
    try:
        while True:
            # Try parse any existing buffered frames first
            while True:
                frame, buf = try_parse_frame(buf)
                if frame is None:
                    break
                if not frame['crc_ok']:
                    if verbose:
                        print('[srv] drop: bad CRC')
                    continue
                mtype = frame['type']
                payload = frame['payload']
                if mtype == MsgType.HELLO:
                    # Respond with HELLO
                    hdr = payload_hello(prog.width, prog.height)
                    conn.sendall(pack_frame(MsgType.HELLO, hdr, seq=seq))
                    seq = (seq + 1) & 0xFFFF
                elif mtype == MsgType.LOAD_CHUNK:
                    try:
                        sid, total, off, chunk = _parse_load_chunk(payload)
                    except Exception as e:
                        if verbose:
                            print(f'[srv] load_chunk parse err: {e}')
                        continue
                    sess = sessions.get(sid)
                    if not sess:
                        sess = {
                            'total': total,
                            'buf': bytearray(total),
                            'written': 0,
                        }
                        sessions[sid] = sess
                    if off + len(chunk) > sess['total']:
                        if verbose:
                            print('[srv] load_chunk overflow ignored')
                        continue
                    sess['buf'][off:off+len(chunk)] = chunk
                    sess['written'] += len(chunk)
                    if verbose:
                        print(f'[srv] chunk sid={sid} off={off} len={len(chunk)} {sess["written"]}/{sess["total"]}')
                elif mtype == MsgType.APPLY:
                    # Find a fully written session (largest id preferred)
                    complete_sid = None
                    for sid, sess in sorted(sessions.items(), key=lambda kv: kv[0], reverse=True):
                        if sess['written'] >= sess['total']:
                            complete_sid = sid
                            break
                    if complete_sid is None:
                        if verbose:
                            print('[srv] apply: no complete session')
                        continue
                    data = bytes(sessions[complete_sid]['buf'])
                    try:
                        meta = emu.load_bitstream(data)
                        if verbose:
                            print(f'[srv] applied sid={complete_sid} used_header={meta["used_header"]} order={meta["order"]}')
                    except Exception as e:
                        if verbose:
                            print(f'[srv] apply error: {e}')
                elif mtype == MsgType.SET_INPUTS:
                    m, _rest = decode_name_u64_map(payload)
                    for k, v in m.items():
                        if k in current_inputs:
                            current_inputs[k] = int(v)
                    if verbose:
                        print(f'[srv] set_inputs: {list(m.keys())}')
                elif mtype == MsgType.STEP:
                    if len(payload) >= 4:
                        import struct
                        cycles = struct.unpack('<I', payload[:4])[0]
                    else:
                        cycles = 1
                    emu.run_stream([current_inputs], cycles_per_step=cycles, reset=False)
                    if verbose:
                        print(f'[srv] step: {cycles}')
                elif mtype == MsgType.GET_OUTPUTS:
                    outputs = emu.sample_outputs(current_inputs)
                    outp = encode_name_u64_map(outputs)
                    conn.sendall(pack_frame(MsgType.OUTPUTS, outp, seq=seq))
                    seq = (seq + 1) & 0xFFFF
                elif mtype == MsgType.QUIT:
                    if verbose:
                        print('[srv] QUIT received; shutting down connection')
                    return
                elif mtype == MsgType.SHUTDOWN:
                    if verbose:
                        print('[srv] SHUTDOWN received; stopping server listener')
                    if shutdown_event is not None:
                        shutdown_event.set()
                    return
                else:
                    if verbose:
                        print(f'[srv] unrecognized msg: {mtype}')

            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            if not data:
                break
            buf += data
    finally:
        if verbose:
            print(f'[srv] disconnected: {peer}')
        conn.close()


def main():
    ap = argparse.ArgumentParser(description='Serve BitGrid Emulator over TCP (BGCF protocol).')
    ap.add_argument('--program', required=True, help='Program JSON (defines dims and I/O mapping)')
    ap.add_argument('--host', default='127.0.0.1', help='Listen address (default 127.0.0.1)')
    ap.add_argument('--port', type=int, default=9000, help='Listen port (default 9000)')
    ap.add_argument('--bitstream', help='Optional bitstream file to preload (headered or raw)')
    ap.add_argument('--verbose', action='store_true', help='Verbose logs')
    args = ap.parse_args()

    prog = Program.load(args.program)
    bs_data = None
    if args.bitstream:
        with open(args.bitstream, 'rb') as f:
            bs_data = f.read()

    shutdown_event = threading.Event()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((args.host, args.port))
        s.listen(1)
        print(f'[srv] listening on {args.host}:{args.port}')
        while True:
            conn, _addr = s.accept()
            handle_client(conn, prog, preloaded_bitstream=bs_data, verbose=args.verbose, shutdown_event=shutdown_event)
            if shutdown_event.is_set():
                if args.verbose:
                    print('[srv] shutting down listener by request')
                break


if __name__ == '__main__':
    main()
