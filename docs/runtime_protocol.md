# BitGrid runtime protocol (sketch)

Goal: a transport-agnostic control + data protocol that works over serial (UART/USB CDC), TCP/UDP (Ethernet/Wi‑Fi), and in‑process pipes. It should configure bitstreams, set inputs, step cycles, and read outputs in a consistent way.

## Layers

- Framing: BGCF (BitGrid Control Frame), little‑endian, CRC‑32; resynchronizable by magic.
- Messages: typed payloads (HELLO, LOAD_CHUNK, APPLY, SET_INPUTS, STEP, GET_OUTPUTS, OUTPUTS, ERROR).
- Transports: serial (8N1), TCP, UDP (optional), UNIX/Win pipes.

## Control frame (BGCF)

Header (16 bytes) + payload:
- magic: 'BGCF'
- version: 1
- type: u8
- flags: u8 (bit0 ack req/reserved)
- seq: u16 (wraparound)
- length: u16 (payload length)
- crc32: u32 (of header fields [version..length] and payload)

See `bitgrid/protocol.py` for pack/parse helpers.

## Key message types

- HELLO (0x01): negotiate grid dims, features
  - payload: u16 width, u16 height, u16 proto_version, u32 features
- LOAD_CHUNK (0x02): send a bitstream in chunks
  - payload: u16 session_id, u32 total_bytes, u32 offset, u16 chunk_len, bytes chunk
- APPLY (0x03): commit loaded bitstream to active config
  - payload: none
- SET_INPUTS (0x05): set input name→value map (u64 per name)
  - payload: TLV: u16 count, repeated {u8 name_len, bytes name, u64 value}
- STEP (0x04): advance N cycles
  - payload: u32 cycles
- GET_OUTPUTS (0x06): request outputs; device responds with OUTPUTS (0x07)
  - payload: none
- OUTPUTS (0x07): name→u64 map of output samples
  - payload: TLV as above
- QUIT (0x08): close the current connection gracefully
  - payload: none
- SHUTDOWN (0x09): stop the server listener/process (for test rigs)
  - payload: none
- LINK (0x0A): request the device to establish an inter-server link to a peer
  - payload: u8 dir_code (0=N,1=E,2=S,3=W), u8 reserved,
    u16 local_out_len, bytes local_out_name,
    u16 remote_in_len, bytes remote_in_name,
    u16 host_len, bytes host, u16 port, u16 lanes (0=auto)
  - Notes: current server implements E (local east -> peer west) only.
- UNLINK (0x0B): tear down any active inter-server link
  - payload: none
- LINK_ACK (0x0C): link established
  - payload: u16 lanes (accepted)
- ERROR (0x7F): error code + message (u16 code, u8 msg_len, bytes msg)

## Data streams

Two categories:
- Configuration: bitstream (headered), delivered via LOAD_CHUNK + APPLY.
- I/O streaming: optional high‑rate streams for inputs/outputs; for simple systems, SET_INPUTS + STEP + GET_OUTPUTS/OUTPUTS is sufficient.

Future extensions:
- Bulk I/O stream messages with sequence numbers and windowing for high‑throughput streaming
- Timestamped OUTPUTS for multi‑device sync
- Compression for LOAD_CHUNK (flagged)

## Transport notes

- Serial: use COBS/SLIP if the underlying link needs byte‑stuffing; BGCF already has magic + CRC, so you can also rely on explicit packetization if the transport provides it (e.g., TCP).
- UDP: add simple acks (flags/seq) or run over QUIC for reliability.
- TCP: framing works as-is; just accumulate and parse.

## Reference helpers

- Python framing/TLV: `bitgrid/protocol.py`
- Bitstream format: `bitgrid/bitstream.py`, header spec in README and `docs/bitstream_header_pascal.md`
- Emulator loader: `bitgrid/cli/emu_load_bitstream.py`

## Minimal device loop (pseudocode)

```
buf = b''
while running:
  buf += recv()
  frame, buf = try_parse_frame(buf)
  if frame is None: continue
  if not frame['crc_ok']: continue
  t = frame['type']
  if t == 0x01: send(pack_frame(0x01, payload_hello(W,H)))
  elif t == 0x02: append_chunk(...)
  elif t == 0x03: apply_loaded_bitstream()
  elif t == 0x05: set_inputs(decode_name_u64_map(frame['payload']))
  elif t == 0x04: step_cycles(...)
  elif t == 0x06: send_outputs()
  elif t == 0x08: close_connection()
  elif t == 0x09: stop_listener_and_exit()
  else: send(pack_frame(0x7F, payload_error(1, 'unknown')))
```

This keeps control simple and portable across Pascal/C++/Python.

## Timing and linked forwarding

- The emulator advances in subcycles: A then B. A full cycle is A+B.
- `STEP`'s `cycles` field is interpreted as subcycles; `cycles=2` advances one full cycle.
- When devices are linked via `LINK/LINK_ACK`, the reference server can forward seam data each subcycle (A and B) and advance the peer by one subcycle per forward. With `cycles=2`, that yields two seam transfers per `STEP`.
- If you instead gate forwarding to B-phase only, you get exactly one seam transfer per full cycle.

Rule of thumb: inserting data along an edge of N adjacent cells just before an A subcycle will emerge at the opposite edge after roughly N/2 full cycles (due to the checkerboard), i.e., just before the next A following those cycles. This enables streaming approximately N characters in N + width/2 + a small constant number of cycles when forwarding every subcycle.
