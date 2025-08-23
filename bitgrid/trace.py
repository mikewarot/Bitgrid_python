from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, TextIO
import json
import csv


@dataclass
class TraceEvent:
    kind: str           # 'tx' | 'rx' | 'aligned'
    tile: str           # tile id (e.g., 'L','R','TL','TR','BL','BR')
    side: Optional[str] # 'N','E','S','W' or None
    epoch: int
    phase: Optional[str]  # 'A'|'B' or None for aligned
    lanes: Optional[List[int]]  # raw lane bits (full list)
    indices: Optional[List[int]]  # which indices are fresh/used
    value: Optional[int]  # numeric value (e.g., aligned vector)


class TraceLogger:
    def __init__(self, path: str, fmt: str = 'jsonl'):
        self.path = path
        self.fmt = fmt.lower()
        self._fh: Optional[TextIO] = open(self.path, 'w', encoding='utf-8')
        self._csvw = None
        if self.fmt == 'csv':
            self._csvw = csv.writer(self._fh)
            self._csvw.writerow(['kind','tile','side','epoch','phase','value','lanes','indices'])

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None

    def log(self, ev: TraceEvent):
        if not self._fh:
            return
        if self.fmt == 'jsonl':
            obj = {
                'kind': ev.kind,
                'tile': ev.tile,
                'side': ev.side,
                'epoch': ev.epoch,
                'phase': ev.phase,
                'value': ev.value,
                'lanes': ev.lanes,
                'indices': ev.indices,
            }
            self._fh.write(json.dumps(obj) + '\n')
        elif self.fmt == 'csv':
            if not self._csvw:
                return
            self._csvw.writerow([
                ev.kind,
                ev.tile,
                ev.side or '',
                ev.epoch,
                ev.phase or '',
                ev.value if ev.value is not None else '',
                ''.join(str(b & 1) for b in (ev.lanes or [])),
                ','.join(str(i) for i in (ev.indices or [])),
            ])
        else:
            # default to jsonl
            self._fh.write(json.dumps(ev.__dict__) + '\n')
