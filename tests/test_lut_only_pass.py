from __future__ import annotations

from bitgrid.lut_only import LUTGrid, LUTOnlyEmulator
from bitgrid.router import route_luts


def make_pass_grid(w: int, h: int) -> LUTGrid:
    g = LUTGrid(w, h)
    for y in range(h):
        for x in range(w):
            # Route W input to E output
            luts = route_luts('E', 'W')
            g.add_cell(x, y, luts)
    return g


def test_west_to_east_propagates_in_two_steps():
    g = make_pass_grid(2, 3)
    emu = LUTOnlyEmulator(g)
    west = [1, 0, 1]
    out1 = emu.step(edge_in={'W': west})
    assert out1['E'] == [0, 0, 0]
    out2 = emu.step(edge_in={'W': [0, 0, 0]})
    assert out2['E'] == west
