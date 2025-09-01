from __future__ import annotations

import argparse
import json
import os
from typing import List, Dict, Any

from ..lut_only import LUTGrid
from ..lut_logic import decompile_lut_to_expr


def build_embedded_model(grid: LUTGrid) -> Dict[str, Any]:
    cells: List[List[Dict[str, Any]]] = []
    for y in range(grid.H):
        row: List[Dict[str, Any]] = []
        for x in range(grid.W):
            luts = grid.cells[y][x].luts
            # Precompute expressions and hex
            exprs = [decompile_lut_to_expr(l) if l else '0' for l in luts]
            hexes = [f"{l & 0xFFFF:04X}" for l in luts]
            row.append({
                'x': x,
                'y': y,
                'luts': luts,
                'hex': hexes,
                'expr': exprs,
            })
        cells.append(row)
    return {'W': grid.W, 'H': grid.H, 'cells': cells}


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>BitGrid LUT Viewer</title>
  <style>
    body { font-family: system-ui, Segoe UI, Roboto, Arial, sans-serif; margin: 0; height: 100vh; display: flex; }
    #grid { flex: 2 1 0; overflow: auto; background: #0b0d12; color: #e6e6e6; padding: 12px; }
    #side { flex: 1 1 320px; border-left: 1px solid #333; padding: 12px; }
    .cell { box-sizing: border-box; border: 1px solid #333; padding: 4px; cursor: pointer; background: #11151c; }
    .cell.empty { opacity: 0.25; }
    .coords { color: #7aa2f7; font-size: 11px; }
    .dirs { margin-top: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; line-height: 1.25; }
    .dir { display: inline-block; margin-right: 6px; }
    .N { color: #5fd7ff; } .E { color: #ffd75f; } .S { color: #87ff87; } .W { color: #ff87ff; }
    .controls { margin-bottom: 8px; }
    .gridwrap { display: grid; gap: 4px; }
    .pill { display:inline-block; background:#1e2430; border:1px solid #394057; border-radius:12px; padding:2px 8px; font-size:11px; margin-right:6px; }
    pre { white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
  </style>
  <script>
    const MODEL = __MODEL__;
    let showExpr = true;
    let showHex = false;
    let filter = {N:true,E:true,S:true,W:true};
    function renderGrid() {
      const wrap = document.getElementById('gridwrap');
      wrap.style.gridTemplateColumns = `repeat(${MODEL.W}, minmax(80px, 1fr))`;
      wrap.innerHTML = '';
      for (let y=0; y<MODEL.H; y++){
        for (let x=0; x<MODEL.W; x++){
          const c = MODEL.cells[y][x];
          const el = document.createElement('div');
          el.className = 'cell' + (c.expr.every(e => e==='0') ? ' empty' : '');
          el.onclick = () => selectCell(c);
          const coords = document.createElement('div'); coords.className = 'coords'; coords.textContent = `(${x},${y})`;
          el.appendChild(coords);
          const dirs = document.createElement('div'); dirs.className = 'dirs';
          const names = ['N','E','S','W'];
          for (let i=0;i<4;i++){
            if (!filter[names[i]]) continue;
            const val = showExpr ? c.expr[i] : (showHex ? c.hex[i] : c.luts[i]);
            if (val && val !== '0' && val !== 0){
              const span = document.createElement('span');
              span.className = 'dir ' + names[i];
              span.textContent = names[i] + '=' + String(val);
              dirs.appendChild(span);
            }
          }
          el.appendChild(dirs);
          wrap.appendChild(el);
        }
      }
    }
    function selectCell(c){
      const names = ['N','E','S','W'];
      const detail = document.getElementById('detail');
      detail.innerHTML = '';
      const h = document.createElement('h3'); h.textContent = `Cell (${c.x},${c.y})`; detail.appendChild(h);
      const meta = document.createElement('div'); meta.innerHTML = `<span class='pill'>${MODEL.W}×${MODEL.H}</span>`; detail.appendChild(meta);
      const sec = document.createElement('div');
      for (let i=0;i<4;i++){
        if (!filter[names[i]]) continue;
        const dir = document.createElement('div'); dir.style.marginTop = '6px';
        const title = document.createElement('div'); title.innerHTML = `<b class='${names[i]}'>${names[i]}</b>`; dir.appendChild(title);
        const ex = document.createElement('pre'); ex.textContent = 'expr: ' + c.expr[i]; dir.appendChild(ex);
        const hx = document.createElement('pre'); hx.textContent = 'lut : 0x' + c.hex[i] + ' (' + c.luts[i] + ')'; dir.appendChild(hx);
        sec.appendChild(dir);
      }
      detail.appendChild(sec);
    }
    function toggleExpr(){ showExpr = true; showHex = false; renderGrid(); }
    function toggleHex(){ showExpr = false; showHex = true; renderGrid(); }
    function toggleRaw(){ showExpr = false; showHex = false; renderGrid(); }
    function setFilter(id, checked){ filter[id] = checked; renderGrid(); }
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
  <div id="side">
    <div id="detail">Click a cell to inspect.</div>
  </div>
</body>
</html>
"""


def write_html(model: Dict[str, Any], out_path: str):
    html = HTML_TEMPLATE.replace('__MODEL__', json.dumps(model))
    html = html.replace('__W__', str(model['W'])).replace('__H__', str(model['H']))
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)


def main():
    ap = argparse.ArgumentParser(description='Export a LUTGrid JSON to a single-file interactive HTML viewer.')
    ap.add_argument('--in', dest='inp', required=True, help='Input LUTGrid JSON file')
    ap.add_argument('--out', dest='out', required=True, help='Output HTML file path')
    args = ap.parse_args()

    grid = LUTGrid.load(args.inp)
    model = build_embedded_model(grid)
    write_html(model, args.out)
    print(f"Wrote {args.out} for LUTGrid {grid.W}x{grid.H}")


if __name__ == '__main__':
    main()
