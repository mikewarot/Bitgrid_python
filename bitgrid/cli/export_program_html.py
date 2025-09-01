from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List, Optional

from ..program import Program, Cell
from ..lut_logic import decompile_lut_to_expr


def _cell_luts(c: Cell) -> List[int]:
    params = c.params or {}
    lparam = params.get('luts', params.get('lut'))
    if isinstance(lparam, (list, tuple)):
        # Ensure length 4 with padding
        arr = [int(lparam[i]) if i < len(lparam) else 0 for i in range(4)]
        return arr
    try:
        v = int(lparam) if lparam is not None else 0
    except Exception:
        v = 0
    return [v, 0, 0, 0]


def build_model(prog: Program) -> Dict[str, Any]:
    W, H = prog.width, prog.height
    grid: List[List[Optional[Cell]]] = [[None for _ in range(W)] for _ in range(H)]
    for c in prog.cells:
        if 0 <= c.y < H and 0 <= c.x < W:
            grid[c.y][c.x] = c
    model_cells: List[List[Dict[str, Any]]] = []
    for y in range(H):
        row: List[Dict[str, Any]] = []
        for x in range(W):
            c = grid[y][x]
            if c is None:
                row.append({'x': x, 'y': y, 'empty': True})
                continue
            luts = _cell_luts(c)
            hexes = [f"{v & 0xFFFF:04X}" for v in luts]
            exprs = [decompile_lut_to_expr(v) if v else '0' for v in luts]
            row.append({
                'x': x,
                'y': y,
                'empty': False,
                'op': c.op,
                'luts': luts,
                'hex': hexes,
                'expr': exprs,
                'inputs': c.inputs or [],
            })
        model_cells.append(row)
    io = {
        'inputs': {k: v for k, v in prog.input_bits.items()},
        'outputs': {k: v for k, v in prog.output_bits.items()},
    }
    return {'W': W, 'H': H, 'cells': model_cells, 'io': io}


HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset=\"UTF-8\" />
  <title>BitGrid Program Viewer</title>
  <style>
    :root { --bg:#0b0d12; --fg:#e6e6e6; --muted:#9aa0aa; --card:#11151c; --border:#30384a; }
    body { margin:0; font-family: system-ui, Segoe UI, Roboto, Arial, sans-serif; color: var(--fg); background: var(--bg); height: 100vh; display: flex; }
    #grid { flex: 2 1 0; overflow: auto; padding: 12px; }
    #side { flex: 1 1 360px; border-left: 1px solid var(--border); padding: 12px; }
    .cell { box-sizing: border-box; border: 1px solid var(--border); padding: 4px; background: var(--card); cursor: pointer; }
    .cell.empty { opacity: .25; cursor: default; }
    .coords { color:#7aa2f7; font-size:11px; }
    .dirs { margin-top:4px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; line-height: 1.25; }
    .dir { display:inline-block; margin-right: 6px; }
    .N { color:#5fd7ff; } .E { color:#ffd75f; } .S { color:#87ff87; } .W { color:#ff87ff; }
    .controls { margin-bottom: 8px; }
    .gridwrap { display:grid; gap:4px; }
    pre { white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
    .pill { display:inline-block; background:#1e2430; border:1px solid #394057; border-radius:12px; padding:2px 8px; font-size:11px; margin-right:6px; }
    .muted { color: var(--muted); }
  </style>
  <script>
    const MODEL = __MODEL__;
    let showExpr = true; let showHex = false;
    let filter = {N:true,E:true,S:true,W:true};
    function renderGrid(){
      const wrap = document.getElementById('gridwrap');
      wrap.style.gridTemplateColumns = `repeat(${MODEL.W}, minmax(90px, 1fr))`;
      wrap.innerHTML = '';
      for (let y=0;y<MODEL.H;y++){
        for (let x=0;x<MODEL.W;x++){
          const c = MODEL.cells[y][x];
          const el = document.createElement('div');
          el.className = 'cell' + (c.empty ? ' empty' : '');
          if (!c.empty){ el.onclick = () => selectCell(c); }
          const coords = document.createElement('div'); coords.className='coords'; coords.textContent=`(${x},${y})` + (c.empty?' •':''); el.appendChild(coords);
          if (!c.empty){
            const op = document.createElement('div'); op.className='muted'; op.textContent = c.op; el.appendChild(op);
            const dirs = document.createElement('div'); dirs.className='dirs';
            const names=['N','E','S','W'];
            for (let i=0;i<4;i++){
              if (!filter[names[i]]) continue;
              const val = showExpr ? c.expr[i] : (showHex ? ('0x'+c.hex[i]) : c.luts[i]);
              if (val && val !== '0' && val !== 0){
                const span = document.createElement('span'); span.className='dir '+names[i];
                span.textContent = names[i]+'='+String(val);
                dirs.appendChild(span);
              }
            }
            el.appendChild(dirs);
          }
          wrap.appendChild(el);
        }
      }
    }
    function selectCell(c){
      const detail = document.getElementById('detail');
      detail.innerHTML = '';
      const h = document.createElement('h3'); h.textContent = `Cell (${c.x},${c.y}) • ${c.op}`; detail.appendChild(h);
      const meta = document.createElement('div'); meta.innerHTML = `<span class='pill'>${MODEL.W}×${MODEL.H}</span>`; detail.appendChild(meta);
      const names=['N','E','S','W'];
      for (let i=0;i<4;i++){
        if (!filter[names[i]]) continue;
        const sec = document.createElement('div'); sec.style.marginTop='8px';
        const title = document.createElement('div'); title.innerHTML = `<b class='${names[i]}'>${names[i]}</b>`; sec.appendChild(title);
        const ex = document.createElement('pre'); ex.textContent = 'expr: ' + c.expr[i]; sec.appendChild(ex);
        const hx = document.createElement('pre'); hx.textContent = 'lut : 0x' + c.hex[i] + ' (' + c.luts[i] + ')'; sec.appendChild(hx);
        detail.appendChild(sec);
      }
      const inp = document.createElement('div'); inp.style.marginTop='12px';
      const hdr = document.createElement('div'); hdr.innerHTML = '<b>inputs</b>'; inp.appendChild(hdr);
      const pre = document.createElement('pre'); pre.textContent = JSON.stringify(c.inputs, null, 2); inp.appendChild(pre);
      detail.appendChild(inp);
    }
    function toggleExpr(){ showExpr=true; showHex=false; renderGrid(); }
    function toggleHex(){ showExpr=false; showHex=true; renderGrid(); }
    function toggleRaw(){ showExpr=false; showHex=false; renderGrid(); }
    function setFilter(id, checked){ filter[id]=checked; renderGrid(); }
    window.onload = () => { renderGrid(); };
  </script>
</head>
<body>
  <div id="grid">
    <div class="controls">
      <span class="pill">W×H: __W__×__H__</span>
      <label><input type="radio" name="fmt" checked onclick="toggleExpr()"> expr</label>
      <label><input type="radio" name="fmt" onclick="toggleHex()"> hex</label>
      <label><input type="radio" name="fmt" onclick="toggleRaw()"> raw</label>
      &nbsp;&nbsp;
      <label><input type="checkbox" checked onchange="setFilter('N', this.checked)"> N</label>
      <label><input type="checkbox" checked onchange="setFilter('E', this.checked)"> E</label>
      <label><input type="checkbox" checked onchange="setFilter('S', this.checked)"> S</label>
      <label><input type="checkbox" checked onchange="setFilter('W', this.checked)"> W</label>
    </div>
    <div id="gridwrap" class="gridwrap"></div>
  </div>
  <div id="side"><div id="detail">Click a non-empty cell to inspect.</div></div>
</body>
</html>
"""


def write_html(model: Dict[str, Any], out_path: str):
    s = HTML.replace('__MODEL__', json.dumps(model))
    s = s.replace('__W__', str(model['W'])).replace('__H__', str(model['H']))
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(s)


def main():
    ap = argparse.ArgumentParser(description='Export a Program JSON to a single-file interactive HTML viewer (no routing required).')
    ap.add_argument('--program', required=True, help='Input Program JSON path')
    ap.add_argument('--out', required=True, help='Output HTML path')
    args = ap.parse_args()

    prog = Program.load(args.program)
    model = build_model(prog)
    write_html(model, args.out)
    print(f"Wrote {args.out} for Program {prog.width}x{prog.height} with {len(prog.cells)} cells")


if __name__ == '__main__':
    main()
