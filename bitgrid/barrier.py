from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


Phase = str  # 'A' or 'B'


@dataclass
class BarrierState:
    epoch: int = 0
    phase: Phase = 'A'


class NeighborBarrier:
    """
    Minimal distributed two-phase barrier over 4-neighbor links.

    Each tile:
      - calls local_done() after it finished computing current (epoch, phase)
      - collects neighbor_done flags from up to 4 neighbors
      - can_advance() returns True when all expected neighbor flags for (epoch, phase) are present
      - advance() moves to next subphase or next epoch
    """
    def __init__(self, expect_north: bool, expect_east: bool, expect_south: bool, expect_west: bool):
        self.state = BarrierState(0, 'A')
        self.expect = {
            'N': expect_north,
            'E': expect_east,
            'S': expect_south,
            'W': expect_west,
        }
        self.neighbor_flags: Dict[Tuple[int, Phase, str], bool] = {}
        self._local_done: Dict[Tuple[int, Phase], bool] = {}

    def local_done(self) -> None:
        key = (self.state.epoch, self.state.phase)
        self._local_done[key] = True

    def mark_neighbor_done(self, direction: str, epoch: int, phase: Phase) -> None:
        if direction not in self.expect:
            return
        self.neighbor_flags[(epoch, phase, direction)] = True

    def can_advance(self) -> bool:
        e, p = self.state.epoch, self.state.phase
        if not self._local_done.get((e, p), False):
            return False
        for d, needed in self.expect.items():
            if not needed:
                continue
            if not self.neighbor_flags.get((e, p, d), False):
                return False
        return True

    def advance(self) -> None:
        if not self.can_advance():
            return
        if self.state.phase == 'A':
            self.state.phase = 'B'
        else:
            self.state.phase = 'A'
            self.state.epoch += 1

    def current(self) -> Tuple[int, Phase]:
        return (self.state.epoch, self.state.phase)
