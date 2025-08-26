from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


@dataclass
class LUTCell:
    x: int
    y: int
    # 4 outputs are computed from 4 inputs via 4 separate 16-bit LUTs
    # luts[0] -> out N, luts[1] -> out E, luts[2] -> out S, luts[3] -> out W
    # Indexing of LUT: idx = N | (E<<1) | (S<<2) | (W<<3)
    luts: List[int]


class LUTGrid:
    def __init__(self, width: int, height: int):
        if width <= 0 or height <= 0:
            raise ValueError("width/height must be positive")
        self.W = width
        self.H = height
        self.cells: Dict[Tuple[int,int], LUTCell] = {}

    def add_cell(self, x: int, y: int, luts: List[int]):
        if not (0 <= x < self.W and 0 <= y < self.H):
            raise ValueError("cell outside grid")
        if len(luts) != 4:
            raise ValueError("luts must have 4 16-bit integers")
        self.cells[(x, y)] = LUTCell(x, y, [int(l) & 0xFFFF for l in luts])


class LUTOnlyEmulator:
    def __init__(self, grid: LUTGrid):
        self.g = grid
        # Per-cell 4-bit outputs N,E,S,W
        self.outs: Dict[Tuple[int,int], List[int]] = { (x,y): [0,0,0,0] for (x,y) in self.g.cells.keys() }
        self._cycle = 0

    def reset(self):
        for k in self.outs.keys():
            self.outs[k] = [0,0,0,0]
        self._cycle = 0

    def _eval_cell(self, cell: LUTCell, in_bits: List[int]) -> List[int]:
        idx = (in_bits[0] & 1) | ((in_bits[1] & 1) << 1) | ((in_bits[2] & 1) << 2) | ((in_bits[3] & 1) << 3)
        return [ (cell.luts[i] >> idx) & 1 for i in range(4) ]

    def _neighbor_out(self, x: int, y: int, dir_name: str) -> Optional[int]:
        # dir_name is one of 'N','E','S','W'; we need to fetch the opposite output from the neighbor cell
        opposite = {'N':'S','E':'W','S':'N','W':'E'}[dir_name]
        dx, dy = {'N':(0,-1), 'E':(1,0), 'S':(0,1), 'W':(-1,0)}[dir_name]
        nx, ny = x+dx, y+dy
        if (nx, ny) in self.outs:
            out_idx = {'N':0,'E':1,'S':2,'W':3}[opposite]
            return self.outs[(nx, ny)][out_idx]
        return None

    def step(self, edge_in: Dict[str, List[int]] | None = None) -> Dict[str, List[int]]:
        """Advance one subcycle (phase). edge_in provides boundary bits:
        - edge_in['N']: length W, drives N input of row 0 cells (as if from outside)
        - edge_in['E']: length H, drives E input of col W-1 cells
        - edge_in['S']: length W, drives S input of row H-1 cells
        - edge_in['W']: length H, drives W input of col 0 cells
        Returns edge_out dict of same shape, sampled from corresponding edge outputs.
        """
        W, H = self.g.W, self.g.H
        edge_in = edge_in or {}
        # Default zeros
        n_in = list(edge_in.get('N', [0]*W))
        e_in = list(edge_in.get('E', [0]*H))
        s_in = list(edge_in.get('S', [0]*W))
        w_in = list(edge_in.get('W', [0]*H))

        phaseA = (self._cycle % 2 == 0)
        new_outs: Dict[Tuple[int,int], List[int]] = {}
        for (x,y), cell in self.g.cells.items():
            is_even = ((x + y) % 2 == 0)
            if (phaseA and not is_even) or ((not phaseA) and is_even):
                continue
            # Gather inputs N,E,S,W
            inN = self._neighbor_out(x, y, 'N')
            if inN is None and y == 0:
                inN = int(n_in[x] if 0 <= x < W else 0)
            inE = self._neighbor_out(x, y, 'E')
            if inE is None and x == W-1:
                inE = int(e_in[y] if 0 <= y < H else 0)
            inS = self._neighbor_out(x, y, 'S')
            if inS is None and y == H-1:
                inS = int(s_in[x] if 0 <= x < W else 0)
            inW = self._neighbor_out(x, y, 'W')
            if inW is None and x == 0:
                inW = int(w_in[y] if 0 <= y < H else 0)
            in_bits = [inN or 0, inE or 0, inS or 0, inW or 0]
            new_outs[(x,y)] = self._eval_cell(cell, in_bits)

        # Commit phase outputs
        for k, v in new_outs.items():
            self.outs[k] = v
        self._cycle += 1

        # Collect edge outputs after update
        edge_out = {
            'N': [0]*W,
            'E': [0]*H,
            'S': [0]*W,
            'W': [0]*H,
        }
        for x in range(W):
            c = self.g.cells.get((x, 0))
            if c and (x,0) in self.outs:
                edge_out['N'][x] = self.outs[(x,0)][0]  # N output
        for y in range(H):
            c = self.g.cells.get((W-1, y))
            if c and (W-1,y) in self.outs:
                edge_out['E'][y] = self.outs[(W-1,y)][1]  # E output
        for x in range(W):
            c = self.g.cells.get((x, H-1))
            if c and (x,H-1) in self.outs:
                edge_out['S'][x] = self.outs[(x,H-1)][2]  # S output
        for y in range(H):
            c = self.g.cells.get((0, y))
            if c and (0,y) in self.outs:
                edge_out['W'][y] = self.outs[(0,y)][3]  # W output
        return edge_out
