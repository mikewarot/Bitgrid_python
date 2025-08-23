from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple


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
    def __init__(self, expect_north: bool, expect_east: bool, expect_south: bool, expect_west: bool, on_event: Optional[Callable[[str, Dict], None]] = None):
        self.state = BarrierState(0, 'A')
        self.expect = {
            'N': expect_north,
            'E': expect_east,
            'S': expect_south,
            'W': expect_west,
        }
        self.neighbor_flags: Dict[Tuple[int, Phase, str], bool] = {}
        self._local_done: Dict[Tuple[int, Phase], bool] = {}
        self._on_event = on_event

    def local_done(self) -> None:
        key = (self.state.epoch, self.state.phase)
        self._local_done[key] = True
        if self._on_event:
            self._on_event('barrier_local_done', {'epoch': key[0], 'phase': key[1], 'status': 'ok'})

    def mark_neighbor_done(self, direction: str, epoch: int, phase: Phase) -> None:
        if direction not in self.expect:
            return
        self.neighbor_flags[(epoch, phase, direction)] = True
        if self._on_event:
            self._on_event('barrier_neighbor_done', {'dir': direction, 'epoch': epoch, 'phase': phase, 'status': 'ok'})

    def mark_neighbor_header(self, direction: str, epoch: int, phase: Phase) -> str:
        """
        Validate neighbor's reported (epoch, phase) and record done.
        Returns: 'ok' | 'unexpected_side' | 'epoch_mismatch' | 'phase_mismatch' | 'duplicate'
        """
        if direction not in self.expect:
            if self._on_event:
                self._on_event('barrier_unexpected_side', {'dir': direction, 'epoch': epoch, 'phase': phase})
            return 'unexpected_side'
        cur_e, cur_p = self.state.epoch, self.state.phase
        status = 'ok'
        if epoch != cur_e:
            status = 'epoch_mismatch'
        elif phase != cur_p:
            status = 'phase_mismatch'
        key = (epoch, phase, direction)
        if self.neighbor_flags.get(key, False):
            status = 'duplicate'
        # Record flag regardless; caller may choose to resync or drop
        self.neighbor_flags[key] = True
        if self._on_event:
            self._on_event('barrier_neighbor_hdr', {'dir': direction, 'epoch': epoch, 'phase': phase, 'status': status, 'expected_epoch': cur_e, 'expected_phase': cur_p})
        return status

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
            if self._on_event:
                e, p = self.state.epoch, self.state.phase
                self._on_event('barrier_cannot_advance', {'epoch': e, 'phase': p, 'status': 'blocked'})
            return
        if self.state.phase == 'A':
            self.state.phase = 'B'
        else:
            self.state.phase = 'A'
            self.state.epoch += 1
        if self._on_event:
            self._on_event('barrier_advance', {'epoch': self.state.epoch, 'phase': self.state.phase, 'status': 'ok'})

    def current(self) -> Tuple[int, Phase]:
        return (self.state.epoch, self.state.phase)
