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
