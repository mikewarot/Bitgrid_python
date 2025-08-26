# LUTGrid JSON format (lutgrid-v1)

This is a simple, editable file format for LUT-only BitGrid programs. It contains only the physical grid
size and the per-cell 4-output LUTs. Missing cells imply zeros (no output activity).

- Top-level fields:
  - `width` (int), `height` (int)
  - `cells`: array of nonzero cells
    - each item: `{ "x": <int>, "y": <int>, "luts": [lutN, lutE, lutS, lutW] }`
      - `luts` are 16-bit integers (0..65535), one per output: N, E, S, W
  - `format`: string identifier; currently `"lutgrid-v1"`

- LUT input pin order: NESW (North, East, South, West)
  - For a 4-input LUT, the truth-table index is: `idx = N | (E<<1) | (S<<2) | (W<<3)`
  - Bit `idx=0` is the output when all inputs are 0; bit `idx=15` is when all inputs are 1.

- Outputs:
  - `luts[0]` drives the North output bit of the cell
  - `luts[1]` drives East, `luts[2]` drives South, `luts[3]` drives West

- Defaults:
  - Any cell not listed in `cells` is treated as `[0,0,0,0]` (all outputs zero)

- Example (2x1 grid, pass West input to East output in both cells):
```json
{
  "width": 2,
  "height": 1,
  "cells": [
    { "x": 0, "y": 0, "luts": [0, 43690, 0, 0] },
    { "x": 1, "y": 0, "luts": [0, 43690, 0, 0] }
  ],
  "format": "lutgrid-v1"
}
```
Notes:
- The value 43690 (0xAAAA) is the LUT that copies the West input to the East output in this format.
- If you need to derive LUT bits programmatically, see `bitgrid.lut_logic.compile_expr_to_lut` or
  `bitgrid.router.route_luts` helpers.

- Execution model:
  - The LUT-only emulator updates cells in two phases (checkerboard A/B) and exchanges signals via NESW neighbors.
  - Edge I/O is injected/read per side: N has width W, E has height H, S has width W, W has height H.

Caveats:
- This format stores only LUTs (no logical netlist). Ensure routing has been applied so that each sink’s intended
  logical input arrives on the correct physical side pin.
