from __future__ import annotations

import argparse
import socket
from typing import Dict, Tuple, List, Optional, TypedDict
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
    payload_step,
    parse_link_payload,
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


class LinkState(TypedDict):
    sock: socket.socket
    host: str
    port: int
    dir: str
    local_out: str
    remote_in: str
    lanes: int
    idxA: List[int]
    idxB: List[int]
    buf_even: List[int]
    buf_odd: List[int]
    cycle: int
    last_sent: int


def handle_client(conn: socket.socket, prog: Program, emu: Emulator, current_inputs: Dict[str, int], sessions: Dict[int, Dict], link_box: Dict[str, Dict[str, LinkState]], lock: threading.Lock, preloaded_bitstream: bytes | None = None, verbose: bool = True, shutdown_event: threading.Event | None = None, link_forward: str = 'both') -> None:
    conn.settimeout(1.0)
    # Link states reference (shared); key -> LinkState
    links: Dict[str, LinkState] = link_box.get('links', {})

    # Helpers for built-in bridging on east seam (left.east -> right.west)
    def _east_fresh_indices(width: int, height: int, phase: str):
        x_east = width - 1
        if phase == 'A':
            return [y for y in range(height) if ((x_east + y) % 2 == 0)]
        else:
            return [y for y in range(height) if ((x_east + y) % 2 == 1)]

    def _pack_bits(bits):
        v = 0
        for i, b in enumerate(bits):
            v |= (int(b) & 1) << i
        return v

    def _unpack_bits(val: int, n: int):
        return [((int(val) >> i) & 1) for i in range(n)]

    def _peer_connect(host: str, port: int, timeout: float = 2.0) -> socket.socket:
        return socket.create_connection((host, port), timeout=timeout)

    def _peer_send_and_recv(sockp: socket.socket, frame: bytes, timeout: float = 2.0):
        sockp.sendall(frame)
        sockp.settimeout(timeout)
        bufp = b''
        while True:
            frame_parsed, bufp = try_parse_frame(bufp)
            if frame_parsed is not None:
                return frame_parsed
            try:
                data = sockp.recv(4096)
            except socket.timeout:
                return None
            if not data:
                return None
            bufp += data

    def _peer_hello(sockp: socket.socket) -> Tuple[int, int]:
        import struct
        resp = _peer_send_and_recv(sockp, pack_frame(MsgType.HELLO, payload_hello(0, 0)))
        if not resp or resp.get('type') != MsgType.HELLO:
            return 0, 0
        payload = resp.get('payload', b'')
        if len(payload) < 10:
            return 0, 0
        width, height, _pv, _feat = struct.unpack('<HHHI', payload[:10])
        return width, height

    if preloaded_bitstream:
        try:
            with lock:
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
                        with lock:
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
                    forwarded = (frame.get('flags', 0) != 0)
                    # If any links, interleave local and peers steps according to forwarding policy.
                    if links and not forwarded:
                        # Group links by peer socket to avoid over-stepping the same peer per subcycle
                        # Make a stable snapshot of current links
                        link_items = list(links.items())
                        for _ in range(int(cycles)):
                            with lock:
                                emu.run_stream([current_inputs], cycles_per_step=1, reset=False)
                            with lock:
                                outs = emu.sample_outputs(current_inputs)
                            # Build groups: sock -> list[(key, linkstate, send_val_or_None)]
                            peer_groups: Dict[socket.socket, List[Tuple[str, LinkState, Optional[int]]]] = {}
                            for key, lk in link_items:
                                lp_sock = lk['sock']
                                local_out_name = lk['local_out']
                                remote_in_name = lk['remote_in']
                                v = int(outs.get(local_out_name, 0))
                                cyc = lk['cycle']
                                last_sent = lk.get('last_sent', 0)
                                # Masks per link (compute once lazily)
                                maskA = maskB = 0
                                if link_forward == 'phase':
                                    for i in lk.get('idxA', []):
                                        maskA |= (1 << int(i))
                                    for i in lk.get('idxB', []):
                                        maskB |= (1 << int(i))
                                send_now = True
                                send_val: Optional[int] = v
                                if link_forward == 'phase':
                                    if (cyc & 1) == 0:
                                        send_val = (last_sent & ~maskA) | (v & maskA)
                                    else:
                                        send_val = (last_sent & ~maskB) | (v & maskB)
                                    last_sent = send_val
                                elif link_forward in ('cycle', 'bonly'):
                                    if (cyc & 1) == 0:
                                        send_now = False
                                        send_val = None
                                    else:
                                        last_sent = v
                                        send_val = v
                                else:
                                    last_sent = v
                                # Update per-link state for next subcycle
                                lk['last_sent'] = last_sent
                                lk['cycle'] = cyc + 1
                                if send_now:
                                    if lp_sock not in peer_groups:
                                        peer_groups[lp_sock] = []
                                    # Store tuple with remote_in name via linkstate
                                    peer_groups[lp_sock].append((key, lk, send_val))
                            # Emit to peers: for each peer, send all SET_INPUTS then one STEP
                            for psock, items in peer_groups.items():
                                for _key, lk, sval in items:
                                    try:
                                        if sval is None:
                                            continue
                                        kv = {lk['remote_in']: int(sval)}
                                        psock.sendall(pack_frame(MsgType.SET_INPUTS, encode_name_u64_map(kv)))
                                    except Exception:
                                        pass
                                try:
                                    psock.sendall(pack_frame(MsgType.STEP, payload_step(1), flags=1))
                                except Exception:
                                    pass
                        if verbose:
                            print(f"[srv] step(linked*): {cycles} on {len(link_items)} link(s)")
                    else:
                        with lock:
                            emu.run_stream([current_inputs], cycles_per_step=cycles, reset=False)
                        if verbose:
                            suffix = ' (fwd)' if forwarded else ''
                            print(f"[srv] step: {cycles}{suffix}")
                elif mtype == MsgType.GET_OUTPUTS:
                    with lock:
                        outputs = emu.sample_outputs(current_inputs)
                    outp = encode_name_u64_map(outputs)
                    conn.sendall(pack_frame(MsgType.OUTPUTS, outp, seq=seq))
                    seq = (seq + 1) & 0xFFFF
                elif mtype == MsgType.LINK:
                    # Establish server-to-server seam link (supports N/E/S/W)
                    try:
                        cfg = parse_link_payload(payload)
                    except Exception as e:
                        if verbose:
                            print(f'[srv] LINK parse error: {e}')
                        continue
                    dir_code = int(cfg.get('dir_code', 1))
                    dir_map = {0: 'N', 1: 'E', 2: 'S', 3: 'W'}
                    dir_char = dir_map.get(dir_code, 'E')
                    host = str(cfg.get('host', '127.0.0.1'))
                    port = int(cfg.get('port', 0))
                    local_out_name = str(cfg.get('local_out', 'east'))
                    remote_in_name = str(cfg.get('remote_in', 'west'))
                    lanes_req = int(cfg.get('lanes', 0))
                    try:
                        psock = _peer_connect(host, port)
                        pw, ph = _peer_hello(psock)
                        if pw == 0 or ph == 0:
                            raise RuntimeError('peer HELLO failed')
                        # Determine seam geometry from the local_out mapping
                        obits = prog.output_bits.get(local_out_name, [])
                        if not obits:
                            raise RuntimeError(f"unknown local_out '{local_out_name}'")
                        # Collect coords per bit if present; otherwise synthesize based on direction
                        coords: List[Tuple[int,int]] = []
                        for i, b in enumerate(obits):
                            if isinstance(b, dict) and ('x' in b and 'y' in b):
                                try:
                                    coords.append((int(b.get('x', 0)), int(b.get('y', 0))))
                                except Exception:
                                    coords.append((0, 0))
                            else:
                                # Synthesize sensible coords based on direction and bit index
                                if dir_char in ('E', 'W'):
                                    sx = prog.width - 1 if dir_char == 'E' else 0
                                    coords.append((sx, i))
                                else:
                                    sy = 0 if dir_char == 'N' else (prog.height - 1)
                                    coords.append((i, sy))
                        lanes_map = len(coords)
                        # Max lanes constrained by peer seam length (vertical -> peer.height, horizontal -> peer.width)
                        max_peer = ph if dir_char in ('E', 'W') else pw
                        lanes = lanes_req if lanes_req > 0 else min(lanes_map, max_peer)
                        # Fresh indices per phase depend on parity of x+y for each bit
                        idxA: List[int] = []
                        idxB: List[int] = []
                        for i in range(lanes):
                            x, y = coords[i]
                            if ((x + y) % 2) == 0:
                                idxA.append(i)
                            else:
                                idxB.append(i)
                        # Create and store new link under a stable key
                        link_key = f"{dir_char}:{local_out_name}->{host}:{port}:{remote_in_name}"
                        link = {
                            'sock': psock,
                            'host': host,
                            'port': port,
                            'dir': dir_char,
                            'local_out': local_out_name,
                            'remote_in': remote_in_name,
                            'lanes': lanes,
                            'idxA': idxA,
                            'idxB': idxB,
                            'buf_even': [0] * lanes,
                            'buf_odd': [0] * lanes,
                            'cycle': 0,
                            'last_sent': 0,
                        }
                        # Save back to shared box and ACK
                        links[link_key] = link
                        link_box['links'] = links
                        from ..protocol import payload_link_ack
                        conn.sendall(pack_frame(MsgType.LINK_ACK, payload_link_ack(lanes)))
                        if verbose:
                            print(f"[srv] LINK established: key='{link_key}', lanes={lanes}")
                    except Exception as e:
                        if verbose:
                            print(f'[srv] LINK failed: {e}')
                        # ensure link cleared
                        from ..protocol import payload_error
                        conn.sendall(pack_frame(MsgType.ERROR, payload_error(1, f'LINK failed: {e}')))
                elif mtype == MsgType.UNLINK:
                    # Close and clear all links (simple UNLINK without payload)
                    for k, lk in list(links.items()):
                        try:
                            s: socket.socket = lk['sock']
                            s.close()
                        except Exception:
                            pass
                        links.pop(k, None)
                    link_box['links'] = links
                    if verbose:
                        print('[srv] UNLINK: cleared all links')
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
        # Cleanup any link peer sockets (best-effort)
        try:
            for lk in list(links.values()):
                try:
                    s: socket.socket = lk['sock']
                    s.close()
                except Exception:
                    pass
        except Exception:
            pass
        if verbose:
            print(f'[srv] disconnected: {peer}')
        conn.close()


def main():
    ap = argparse.ArgumentParser(description='Serve BitGrid Emulator over TCP (BGCF protocol).')
    ap.add_argument('--program', required=True, help='Program JSON (defines dims and I/O mapping)')
    ap.add_argument('--host', default='127.0.0.1', help='Listen address (default 127.0.0.1)')
    ap.add_argument('--port', type=int, default=9000, help='Listen port (default 9000)')
    ap.add_argument('--bitstream', help='Optional bitstream file to preload (headered or raw)')
    ap.add_argument('--link-forward', choices=['both', 'phase', 'cycle', 'bonly'], default='both', help='Seam forwarding policy: both=subcycle send; phase=send only fresh lanes per phase; cycle/bonly=send on B only')
    ap.add_argument('--verbose', action='store_true', help='Verbose logs')
    args = ap.parse_args()

    prog = Program.load(args.program)
    bs_data = None
    if args.bitstream:
        with open(args.bitstream, 'rb') as f:
            bs_data = f.read()

    shutdown_event = threading.Event()
    # Shared emulator and state across connections
    emu = Emulator(prog)
    current_inputs: Dict[str, int] = {name: 0 for name in prog.input_bits.keys()}
    sessions: Dict[int, Dict] = {}
    link_box: Dict[str, Dict[str, LinkState]] = {'links': {}}
    lock = threading.Lock()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((args.host, args.port))
        s.listen(8)
        s.settimeout(0.5)
        print(f'[srv] listening on {args.host}:{args.port}')
        while True:
            try:
                conn, _addr = s.accept()
            except socket.timeout:
                if shutdown_event.is_set():
                    if args.verbose:
                        print('[srv] shutting down listener by request')
                    break
                continue
            t = threading.Thread(target=handle_client, args=(conn, prog, emu, current_inputs, sessions, link_box, lock), kwargs={'preloaded_bitstream': bs_data, 'verbose': args.verbose, 'shutdown_event': shutdown_event, 'link_forward': args.link_forward}, daemon=True)
            t.start()
            if shutdown_event.is_set():
                if args.verbose:
                    print('[srv] shutting down listener by request')
                break


if __name__ == '__main__':
    main()
