// Go board: replaying moves with captures, and drawing a position as SVG.
// Points are SGF strings ("pd"); "" is a pass. Coordinates are never shown to the child.

const SVG = "http://www.w3.org/2000/svg";

export function toXY(p) {
  if (!p || p.length !== 2) return null;
  return [p.charCodeAt(0) - 97, p.charCodeAt(1) - 97];
}

export function toPoint(x, y) {
  return String.fromCharCode(97 + x) + String.fromCharCode(97 + y);
}

export class Position {
  constructor(size, stones) {
    this.size = size;
    this.stones = new Map(stones || []); // point -> "B" | "W"
  }

  static setup(size, setup) {
    const pos = new Position(size);
    for (const p of setup?.B || []) pos.stones.set(p, "B");
    for (const p of setup?.W || []) pos.stones.set(p, "W");
    return pos;
  }

  copy() {
    return new Position(this.size, this.stones);
  }

  neighbors(p) {
    const [x, y] = toXY(p);
    const out = [];
    for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      const nx = x + dx, ny = y + dy;
      if (nx >= 0 && ny >= 0 && nx < this.size && ny < this.size) out.push(toPoint(nx, ny));
    }
    return out;
  }

  group(p) {
    const color = this.stones.get(p);
    const stones = new Set([p]);
    const libs = new Set();
    const todo = [p];
    while (todo.length) {
      const q = todo.pop();
      for (const n of this.neighbors(q)) {
        const c = this.stones.get(n);
        if (!c) libs.add(n);
        else if (c === color && !stones.has(n)) { stones.add(n); todo.push(n); }
      }
    }
    return { stones, libs };
  }

  // Plays a move and returns the captured points. Occupied points are ignored.
  play(color, p) {
    if (!p || this.stones.has(p)) return [];
    this.stones.set(p, color);
    const enemy = color === "B" ? "W" : "B";
    const captured = [];
    for (const n of this.neighbors(p)) {
      if (this.stones.get(n) !== enemy) continue;
      const g = this.group(n);
      if (g.libs.size === 0) for (const s of g.stones) { this.stones.delete(s); captured.push(s); }
    }
    if (!captured.length) {
      const g = this.group(p);
      if (g.libs.size === 0) for (const s of g.stones) this.stones.delete(s);
    }
    return captured;
  }
}

export function positionAt(game, moveIndex) {
  const pos = Position.setup(game.board, game.setup);
  for (const [color, p] of game.moves.slice(0, moveIndex)) pos.play(color, p);
  return pos;
}

function el(name, attrs, parent) {
  const node = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

const STARS = { 19: [3, 9, 15], 13: [3, 6, 9], 9: [2, 4, 6] };

// Draws `view` into an <svg>:
//   view.position: Position; view.last: point of the last move;
//   view.marks: [{label, type: point|group|area, point|points, role}];
//   view.numbers: Map(point -> number) for variation stones; view.guess: point.
export function draw(svg, view) {
  const size = view.position.size;
  const cell = 10;
  const pad = cell * 0.8;
  const full = pad * 2 + cell * (size - 1);
  svg.setAttribute("viewBox", `0 0 ${full} ${full}`);
  svg.replaceChildren();
  const at = (i) => pad + i * cell;

  el("rect", { x: 0, y: 0, width: full, height: full, rx: 2, class: "wood" }, svg);
  const grid = el("g", { class: "grid" }, svg);
  for (let i = 0; i < size; i++) {
    el("line", { x1: at(0), y1: at(i), x2: at(size - 1), y2: at(i) }, grid);
    el("line", { x1: at(i), y1: at(0), x2: at(i), y2: at(size - 1) }, grid);
  }
  for (const x of STARS[size] || []) for (const y of STARS[size] || []) {
    el("circle", { cx: at(x), cy: at(y), r: 0.9, class: "star" }, svg);
  }

  // Territory that changes hands: small squares under everything else.
  for (const m of view.marks || []) {
    if (m.type !== "area") continue;
    for (const p of m.points) {
      const [x, y] = toXY(p);
      el("rect", { x: at(x) - 2.2, y: at(y) - 2.2, width: 4.4, height: 4.4, class: "area" }, svg);
    }
  }

  for (const [p, color] of view.position.stones) {
    const [x, y] = toXY(p);
    el("circle", { cx: at(x), cy: at(y), r: cell * 0.47, class: color === "B" ? "stone black" : "stone white" }, svg);
  }

  const textOn = (p, text, cls) => {
    const [x, y] = toXY(p);
    const t = el("text", { x: at(x), y: at(y) + 0.2, class: cls }, svg);
    t.textContent = text;
  };
  const onColor = (p) => (view.position.stones.get(p) === "B" ? "on-black" : view.position.stones.get(p) === "W" ? "on-white" : "on-empty");

  for (const m of view.marks || []) {
    if (m.type !== "group") continue;
    for (const p of m.points) {
      if (!view.position.stones.has(p)) continue;
      const [x, y] = toXY(p);
      const cx = at(x), cy = at(y);
      const cls = `shape ${onColor(p)} ${m.label === "△" || m.label === "□" ? "hollow" : "filled"}`;
      if (m.label === "▲" || m.label === "△") {
        el("polygon", { points: `${cx},${cy - 2.9} ${cx - 2.6},${cy + 1.7} ${cx + 2.6},${cy + 1.7}`, class: cls }, svg);
      } else {
        el("rect", { x: cx - 2.1, y: cy - 2.1, width: 4.2, height: 4.2, class: cls }, svg);
      }
    }
  }

  if (view.last && view.position.stones.has(view.last) && !(view.numbers && view.numbers.has(view.last))) {
    const [x, y] = toXY(view.last);
    el("circle", { cx: at(x), cy: at(y), r: 2.2, class: `last ${onColor(view.last)}` }, svg);
  }

  for (const m of view.marks || []) {
    if (m.type !== "point") continue;
    const p = m.point;
    const [x, y] = toXY(p);
    if (m.label === "✕") {
      const cx = at(x), cy = at(y), d = 2.6;
      const g = el("g", { class: "cross" }, svg);
      el("line", { x1: cx - d, y1: cy - d, x2: cx + d, y2: cy + d }, g);
      el("line", { x1: cx - d, y1: cy + d, x2: cx + d, y2: cy - d }, g);
      continue;
    }
    if (!view.position.stones.has(p)) {
      el("circle", { cx: at(x), cy: at(y), r: 4.1, class: `badge ${m.role}` }, svg);
      textOn(p, m.label, "label on-badge");
    } else {
      textOn(p, m.label, `label ${onColor(p)}`);
    }
  }

  if (view.numbers) {
    for (const [p, n] of view.numbers) {
      if (view.position.stones.has(p)) textOn(p, String(n), `num ${onColor(p)}`);
    }
  }

  if (view.guess) {
    const [x, y] = toXY(view.guess);
    el("circle", { cx: at(x), cy: at(y), r: 3.6, class: "guess" }, svg);
  }

  return { pad, cell, full };
}

// Converts a click on the board into the nearest SGF point (or null).
export function pointFromEvent(svg, event, size) {
  const rect = svg.getBoundingClientRect();
  const box = svg.viewBox.baseVal;
  const sx = ((event.clientX - rect.left) / rect.width) * box.width;
  const sy = ((event.clientY - rect.top) / rect.height) * box.height;
  const cell = 10, pad = cell * 0.8;
  const x = Math.round((sx - pad) / cell), y = Math.round((sy - pad) / cell);
  if (x < 0 || y < 0 || x >= size || y >= size) return null;
  return toPoint(x, y);
}
