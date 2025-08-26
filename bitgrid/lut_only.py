from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict
from .program import Program


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
        # Dense 2D grid [y][x] of LUTCell; default cells output zeros (all LUTs=0)
        self.cells: List[List[LUTCell]] = [
            [LUTCell(x, y, [0, 0, 0, 0]) for x in range(self.W)]
            for y in range(self.H)
        ]

    def add_cell(self, x: int, y: int, luts: List[int]):
        if not (0 <= x < self.W and 0 <= y < self.H):
            raise ValueError("cell outside grid")
        if len(luts) != 4:
            raise ValueError("luts must have 4 16-bit integers")
        self.cells[y][x] = LUTCell(x, y, [int(l) & 0xFFFF for l in luts])

    # ---- Serialization helpers for editable LUT-only files ----
    def to_json(self) -> str:
        import json
        data = {
            'width': self.W,
            'height': self.H,
            # store only non-zero cells for compactness; missing cells imply [0,0,0,0]
            'cells': [
                {'x': c.x, 'y': c.y, 'luts': list(map(int, c.luts))}
                for row in self.cells for c in row
                if any(v != 0 for v in c.luts)
            ],
            'format': 'lutgrid-v1'
        }
        return json.dumps(data, indent=2)

    @staticmethod
    def from_json(s: str) -> 'LUTGrid':
        import json
        j = json.loads(s)
        g = LUTGrid(int(j['width']), int(j['height']))
        for cell in j.get('cells', []):
            x, y = int(cell['x']), int(cell['y'])
            luts = [int(v) & 0xFFFF for v in cell['luts']]
            g.add_cell(x, y, luts)
        return g

    def save(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @staticmethod
    def load(path: str) -> 'LUTGrid':
        with open(path, 'r', encoding='utf-8') as f:
            return LUTGrid.from_json(f.read())


class LUTOnlyEmulator:
    def __init__(self, grid: LUTGrid):
        self.g = grid
        # Per-cell 4-bit outputs N,E,S,W as dense [y][x]
        self.outs: List[List[List[int]]] = [
            [[0, 0, 0, 0] for _ in range(self.g.W)]
            for _ in range(self.g.H)
        ]
        self._cycle = 0

    def reset(self):
        for y in range(self.g.H):
            for x in range(self.g.W):
                self.outs[y][x] = [0,0,0,0]
        self._cycle = 0

    def _eval_cell(self, cell: LUTCell, in_bits: List[int]) -> List[int]:
        idx = (in_bits[0] & 1) | ((in_bits[1] & 1) << 1) | ((in_bits[2] & 1) << 2) | ((in_bits[3] & 1) << 3)
        return [ (cell.luts[i] >> idx) & 1 for i in range(4) ]

    def _neighbor_out(self, x: int, y: int, dir_name: str) -> Optional[int]:
        # dir_name is one of 'N','E','S','W'; we need to fetch the opposite output from the neighbor cell
        opposite = {'N':'S','E':'W','S':'N','W':'E'}[dir_name]
        dx, dy = {'N':(0,-1), 'E':(1,0), 'S':(0,1), 'W':(-1,0)}[dir_name]
        nx, ny = x+dx, y+dy
        if 0 <= nx < self.g.W and 0 <= ny < self.g.H:
            out_idx = {'N':0,'E':1,'S':2,'W':3}[opposite]
            return self.outs[ny][nx][out_idx]
        return None

    def step(self, edge_in: Optional[Dict[str, List[int]]] = None) -> Dict[str, List[int]]:
        """Advance one subcycle (phase). edge_in provides boundary bits:
        - edge_in['N']: length W, drives N input of row 0 cells (as if from outside)
        - edge_in['E']: length H, drives E input of col W-1 cells
        - edge_in['S']: length W, drives S input of row H-1 cells
        - edge_in['W']: length H, drives W input of col 0 cells
        Returns edge_out dict of same shape, sampled from corresponding edge outputs.
        """
        W, H = self.g.W, self.g.H
        ein: Dict[str, List[int]] = edge_in or {}
        # Default zeros
        n_in = list(ein.get('N', [0]*W))
        e_in = list(ein.get('E', [0]*H))
        s_in = list(ein.get('S', [0]*W))
        w_in = list(ein.get('W', [0]*H))

        phaseA = (self._cycle % 2 == 0)
        # Collect updates for active parity without interfering with reads
        updates: List[tuple[int,int,List[int]]] = []
        for y in range(H):
            for x in range(W):
                cell = self.g.cells[y][x]
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
                updates.append((x, y, self._eval_cell(cell, in_bits)))

        # Commit phase outputs
        for x, y, v in updates:
            self.outs[y][x] = v
        self._cycle += 1

        # Collect edge outputs after update
        edge_out = {
            'N': [0]*W,
            'E': [0]*H,
            'S': [0]*W,
            'W': [0]*H,
        }
        for x in range(W):
            edge_out['N'][x] = self.outs[0][x][0]
        for y in range(H):
            edge_out['E'][y] = self.outs[y][W-1][1]
        for x in range(W):
            edge_out['S'][x] = self.outs[H-1][x][2]
        for y in range(H):
            edge_out['W'][y] = self.outs[y][0][3]
        return edge_out


def grid_from_program(prog: Program, strict: bool = True) -> LUTGrid:
    """Convert a (neighbor-only) Program into a LUTGrid for the LUT-only emulator.
    Requirements:
    - Each cell must provide 4 LUTs in params['luts'] (op 'LUT' or 'ROUTE4').
    - If strict=True, verify all cell inputs of type 'cell' are adjacent (Manhattan distance 1).
      For general programs, run the routing pass first to insert ROUTE4 hops.
    Note: The LUT-only emulator ignores Program.inputs wiring at runtime and uses
    physical NESW neighbor outputs. The routing step must ensure that the intended
    logical inputs arrive on the correct physical side pins of each sink cell.
    """
    g = LUTGrid(prog.width, prog.height)
    if strict:
        for c in prog.cells:
            sx, sy = c.x, c.y
            for src in c.inputs:
                if src.get('type') != 'cell':
                    continue
                try:
                    tx, ty = int(src['x']), int(src['y'])
                except Exception:
                    continue
                if abs(tx - sx) + abs(ty - sy) > 1:
                    raise ValueError(f"Non-neighbor input found for cell {(sx,sy)} from {(tx,ty)}; route the program first.")
    for c in prog.cells:
        luts = c.params.get('luts') if isinstance(c.params, dict) else None
        if not luts or len(luts) != 4:
            raise ValueError(f"Cell at {(c.x,c.y)} missing 4-LUT params; got {luts}")
        g.add_cell(c.x, c.y, [int(v) & 0xFFFF for v in luts])
    return g
