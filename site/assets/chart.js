// Score-lead chart: the child's lead in points (never winrate), key points as coloured dots.

const SVG = "http://www.w3.org/2000/svg";

function el(name, attrs, parent) {
  const node = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

export function drawCurve(svg, curve, keyPoints, onPick) {
  const W = 600, H = 180, left = 34, right = 8, top = 10, bottom = 22;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.replaceChildren();
  const n = Math.max(1, curve.length - 1);
  const maxAbs = Math.max(10, ...curve.map((c) => Math.abs(c.scoreLead)));
  const lim = Math.ceil(maxAbs / 10) * 10;
  const X = (m) => left + ((W - left - right) * m) / n;
  const Y = (v) => top + ((H - top - bottom) * (lim - v)) / (2 * lim);

  for (const v of [-lim, -lim / 2, 0, lim / 2, lim]) {
    el("line", { x1: left, x2: W - right, y1: Y(v), y2: Y(v), class: v === 0 ? "axis zero" : "axis" }, svg);
    const t = el("text", { x: left - 4, y: Y(v) + 3, class: "tick", "text-anchor": "end" }, svg);
    t.textContent = v > 0 ? `+${v}` : String(v);
  }
  for (let m = 50; m < n; m += 50) {
    const t = el("text", { x: X(m), y: H - 6, class: "tick", "text-anchor": "middle" }, svg);
    t.textContent = `${m}手`;
  }

  // Shade above zero (you lead) and below (opponent leads) with two clip paths.
  const pts = curve.map((c) => `${X(c.move)},${Y(c.scoreLead)}`).join(" ");
  const area = `${X(0)},${Y(0)} ${pts} ${X(n)},${Y(0)}`;
  const defs = el("defs", {}, svg);
  const id = "c" + Math.random().toString(36).slice(2, 8);
  el("rect", { x: 0, y: 0, width: W, height: Y(0) }, el("clipPath", { id: id + "u" }, defs));
  el("rect", { x: 0, y: Y(0), width: W, height: H }, el("clipPath", { id: id + "d" }, defs));
  el("polygon", { points: area, class: "lead-up", "clip-path": `url(#${id}u)` }, svg);
  el("polygon", { points: area, class: "lead-down", "clip-path": `url(#${id}d)` }, svg);
  el("polyline", { points: pts, class: "lead-line" }, svg);

  for (const k of keyPoints) {
    const c = curve[Math.min(k.move, curve.length - 1)];
    const g = el("g", { class: `dot ${k.kind}`, tabindex: 0, role: "button" }, svg);
    el("circle", { cx: X(k.move), cy: Y(c.scoreLead), r: 9, class: "hit" }, g);
    el("circle", { cx: X(k.move), cy: Y(c.scoreLead), r: 5 }, g);
    const title = el("title", {}, g);
    title.textContent = `第 ${k.move} 手：${k.title}`;
    g.addEventListener("click", () => onPick(k));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter") onPick(k); });
  }
}
