# BitGrid Tiling and Interop Design

Goal: run one logical BitGrid across multiple smaller emulated tiles (or ASIC tiles) arranged in a 2D array. Each tile is a W×H checkerboard with two-phase updates (A: even parity, B: odd parity). We need a boundary protocol that:
- Moves edge signals between neighboring tiles reliably.
- Preserves the two-phase timing so logic behaves like a single large grid.
- Is simple enough for small MCUs and also ASIC-friendly.

## Model recap
- Cell inputs are ordered N,E,S,W. LUT index uses bits [N,E,S,W] → idx = N | (E<<1) | (S<<2) | (W<<3).
- Two-phase: phase A updates even (x+y)%2==0; phase B updates odd. Outputs are visible immediately to neighbors within the same phase step.
- ROUTE4 hop = 1 cell, 1 phase step per hop.

## Tile boundary contract
Each tile exposes up to 4 edge buses: north, east, south, west. For each edge, we export and import per-row/column bits.

- North edge: export N_out[y] = cell(x,0).outN for all x along top row; import N_in[y] that feeds as W/S/E/N pins of top-row neighbor cells depending on routing.
- More concretely for emulation: we don’t need per-pin; we need the value that would be observed by a neighbor’s opposing edge (matching ROUTE4 semantics).

We define per-edge logical lanes equal to the number of cells along that edge:
- North/South: lanes = tile width (one lane per column).
- East/West: lanes = tile height (one lane per row).

Each lane carries one bit per phase step.

### Timing alignment
To preserve global semantics with cps cycles per input step:
- On phase A: tiles produce A-parity edge outputs; neighbors must capture them and present as inputs for their phase B step (and vice versa). This is equivalent to half-step retiming across the seam.
- Practically, we batch both A and B transfers per emulator cycle (cps=2). For cps=1, we alternate single-edge phases with double-buffering.

### Wire directions at seams
We mirror ROUTE4 behavior at the seam:
- East seam: a bit leaving tile L at (x=W-1, y) onto its east output corresponds to the west input of tile R at (x=0, y). No turn; straight-through.
- Similarly map N↔S and W↔E.

## Transport framing
We define a lightweight frame per emulator cycle (covering both phases when cps=2):
- Header: cycle_id (optional), parity_mask (optional).
- Payload: N_out[W] + E_out[H] + S_out[W] + W_out[H].
- Response provides matching N_in/E_in/S_in/W_in to the neighbor.

For MCU links (UART/SPI/I2C), a fixed-size frame with CRC8 is sufficient. For ASIC, simple parallel buses with ready/valid per edge or source-synchronous strobes.

## MCU-friendly protocol (v0)
- Fixed W,H known at build-time per tile.
- One frame per cps cycles:
  - TX payload: N_out||E_out||S_out||W_out (bit-packed LSB-first per lane index).
  - RX payload: neighbor’s opposing edges in the same order.
- Double-buffer the edge registers so compute of phase A can use last cycle’s imports and export this cycle’s outputs.
- CRC8 (poly 0x07) appended to TX; drop frame on CRC error and hold last-good values.

## Emulator integration plan
- Add EdgePort abstraction to Program: describe which cells drive edge lanes and which cells consume imports at the boundary. (Initial: auto-wire perimeter cells by direction index.)
- Add InterTileLink: packs/unpacks edge lanes into byte arrays.
- Add a new emulator mode: step_with_links(links, cps) → collects edge outputs, exchanges with neighbors (callback/hook), then performs next phase.

## ASIC notes
- Keep the same lane ordering and phase alignment. For TinyTapeout, expose serial shift chains per edge and a clock-enables scheme for A/B phases.
- Provide scan-friendly edge FIFOs for CDC if needed.

## Open questions
- Flow control/backpressure for MCU links (retry vs. hold-last-good).
- Multi-hop tiling latency accounting (global K across tile boundaries).
- Discoverability/ID and topology enumeration for dynamic mesh assemblies.
