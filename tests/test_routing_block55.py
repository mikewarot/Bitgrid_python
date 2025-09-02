from __future__ import annotations

import pytest

from bitgrid.router import ManhattanRouter
from bitgrid.program import Program, Cell
from bitgrid.lut_only import grid_from_program, LUTGrid
from bitgrid.validator import validate_lutgrid_connectivity


def build_parallel8_with_block_55() -> LUTGrid:
    W, H = 10, 10
    prog = Program(width=W, height=H, cells=[], input_bits={}, output_bits={}, latency=0)
    r = ManhattanRouter(W, H)
    # Block the specified cell
    r.occupy(5, 5)
    # Route 8 lanes W->E on rows 0..7
    hop_counts = []
    for row in range(8):
        cells, hops = r.wire_edge_to_edge('W', row, 'E', row)
        prog.cells.extend(cells)
        hop_counts.append(hops)
    # Build LUTGrid
    g = grid_from_program(prog, strict=True)
    return g


def test_corner_mapping_block55_south_from_west():
    g = build_parallel8_with_block_55()
    # Corner before the blocked (5,5) should dogleg down at (4,5): S=W
    c = g.cells[5][4]  # y=5, x=4
    s_lut = int(c.luts[2]) & 0xFFFF
    # 0xFF00 means output equals W input (variable mask for bit3)
    assert s_lut == 0xFF00, f"Expected (4,5) S=W (0xFF00), got 0x{s_lut:04X}"


def test_connectivity_block55_end_to_end_validator():
    g = build_parallel8_with_block_55()
    issues = validate_lutgrid_connectivity(g)
    assert not issues, f"Connectivity issues found: {issues}"
