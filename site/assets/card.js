// Shared by the game page and the habits page: key-point cards, the whole-game board and helpers.

import { draw, pointFromEvent, positionAt, territoryCounts } from "./board.js";

export const KIND = {
  mistake: { label: "错误", icon: "✗" },
  missed_punish: { label: "没惩罚对方", icon: "!" },
  missed_urgent: { label: "漏掉急所", icon: "!" },
  good: { label: "好棋", icon: "★" },
};
export const COLOR_ZH = { B: "黑", W: "白" };

export function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null) node.append(c);
  return node;
}

// Marks and letters are shown in a pill so they stand out in sentences.
export function richText(text) {
  const out = [];
  const re = /([▲△■□✕]|(?<![A-Za-z])[AB](?![A-Za-z]))/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const cls = m[0] === "✕" ? "played" : m[0] === "A" ? "recommended" : m[0] === "B" ? "alt" : "group";
    out.push(h("span", { class: `pill ${cls}` }, m[0]));
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}

// LizzieYzy-style list of the points the AI would consider, with how much each costs
// against its first choice.  Only that first choice says "最好"; rows less than half a point
// behind it say "差不多".
export function candidateTable(list) {
  const rows = (list || []).filter((c) => c.label && c.diff != null);
  if (rows.length < 2) return null;
  return h("table", { class: "cands" },
    h("thead", {}, h("tr", {}, h("th", {}, "下在"), h("th", {}, "比最好的差"), h("th", {}, "说明"))),
    h("tbody", {}, rows.map((c) => h("tr", { class: c.role === "played" ? "played" : "" },
      h("td", {}, richText(c.label)),
      h("td", {}, c.first ? "最好" : c.diff < 0.5 ? "差不多" : `约 ${Math.round(c.diff)} 目`),
      h("td", {}, c.note || "")))));
}

// The 形势 line under a board: who leads (from the student's side) and each side's points.
export function situation(lead, territory, komi) {
  if (lead == null || !territory) return [h("span", { class: "no-data" }, "这一步没有形势数据。")];
  const n = Math.round(Math.abs(lead));
  const text = n < 1 ? "双方差不多" : lead > 0 ? `你领先约 ${n} 目` : `对方领先约 ${n} 目`;
  const { black, white } = territoryCounts(territory);
  return [
    h("span", { class: `lead ${n < 1 ? "" : lead > 0 ? "up" : "down"}` }, text),
    h("span", { class: "counts" },
      `黑约 ${Math.round(black)}，白约 ${Math.round(white)}` + (komi ? `（白另有贴目 ${komi}）` : "")),
  ];
}

// A "形势" toggle with the line it controls; `onChange(on)` redraws the board.
export function situationBar(onChange) {
  const info = h("span", { class: "situation-info" });
  const btn = h("button", { class: "toggle", type: "button", "aria-pressed": "false" }, "形势");
  let on = false;
  const set = (value) => {
    on = value;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", String(on));
    info.hidden = !on;
    onChange(on);
  };
  btn.addEventListener("click", () => set(!on));
  info.hidden = true;
  return { node: h("div", { class: "situation" }, btn, info), info, isOn: () => on, set };
}

// Whole game, move by move, with the 形势 view of each position.
export function replayBoard(data) {
  const game = data.game;
  const total = game.moves.length;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "board");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "棋盘");
  let move = total;
  const slider = h("input", { type: "range", min: "0", max: String(total), value: String(total), "aria-label": "第几手" });
  const prevBtn = h("button", { class: "nav", type: "button", "aria-label": "上一手" }, "‹");
  const nextBtn = h("button", { class: "nav", type: "button", "aria-label": "下一手" }, "›");
  const label = h("p", { class: "move-no" });
  const bar = situationBar(() => render());

  function render() {
    const pos = positionAt(game, move);
    const territory = bar.isOn() ? data.territory?.[move] : null;
    draw(svg, { position: pos, last: game.moves[move - 1]?.[1], territory });
    slider.value = String(move);
    prevBtn.disabled = move === 0;
    nextBtn.disabled = move === total;
    const played = game.moves[move - 1];
    label.textContent = move === 0 ? "开局" : `第 ${move} 手（${COLOR_ZH[played[0]]}${played[1] ? "" : "，停一手"}）`;
    if (bar.isOn()) bar.info.replaceChildren(...situation(data.curve[move]?.scoreLead, data.territory?.[move], game.komi));
  }
  const go = (m) => { move = Math.max(0, Math.min(total, m)); render(); };
  slider.addEventListener("input", () => go(Number(slider.value)));
  prevBtn.addEventListener("click", () => go(move - 1));
  nextBtn.addEventListener("click", () => go(move + 1));
  let touchX = null;
  svg.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; }, { passive: true });
  svg.addEventListener("touchend", (e) => {
    if (touchX === null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    touchX = null;
    if (Math.abs(dx) > 40) go(move + (dx < 0 ? 1 : -1));
  });
  render();
  const section = h("section", { class: "replay" },
    h("h2", {}, "整盘棋"),
    h("p", { class: "legend" }, "拖动滑块看每一手；点“形势”看 AI 估计的每块地归谁。"),
    h("div", { class: "board-wrap" }, svg,
      h("div", { class: "scrub" }, prevBtn, slider, nextBtn), label, bar.node));
  section.goTo = go;
  section.showSituation = bar.set;
  return section;
}

// One key point: the position as a question, then the answer with marks, variations and 形势.
// `opts.heading` replaces "第 N 手：" and `opts.id` the element id; `opts.onGuess(result)` is told
// "right" / "close" / "wrong" when the child taps a point (the practice page keeps score with it).
export function keyPointCard(data, k, opts = {}) {
  const game = data.game;
  const base = positionAt(game, k.position.moveIndex);
  const prevMove = game.moves[k.position.moveIndex - 1];
  const state = { mode: "question", line: null, step: 0, guess: null };
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "board");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "棋盘");

  const stepLabel = h("span", { class: "step" });
  const prevBtn = h("button", { class: "nav", type: "button", "aria-label": "上一步" }, "‹");
  const nextBtn = h("button", { class: "nav", type: "button", "aria-label": "下一步" }, "›");
  // Back to the position of the question, with the marks, from any variation step.
  const resetBtn = h("button", { class: "reset", type: "button", onclick: () => reset() }, "↺ 回到原图");
  const lineBtns = k.lines.map((line, i) =>
    h("button", { class: "line", type: "button", onclick: () => selectLine(i) }, line.name));
  const bar = situationBar(() => render());
  const controls = h("div", { class: "controls", hidden: "" },
    h("div", { class: "lines" }, lineBtns, resetBtn),
    h("div", { class: "stepper" }, prevBtn, stepLabel, nextBtn),
    bar.node);
  const feedback = h("p", { class: "feedback", hidden: "" });

  function render() {
    let view, lead = null, territory = null;
    if (state.mode === "question") {
      view = { position: base, last: prevMove?.[1], guess: state.guess };
    } else if (state.line === null || state.step === 0) {
      view = { position: base, last: prevMove?.[1], marks: k.marks, guess: state.guess };
      lead = data.curve[k.position.moveIndex]?.scoreLead;
      territory = data.territory?.[k.position.moveIndex];
    } else {
      const pos = base.copy();
      const numbers = new Map();
      const moves = k.lines[state.line].moves;
      // Every line starts with the student's move from the position shown.
      let color = game.moves[k.position.moveIndex][0];
      for (let i = 0; i < state.step; i++) {
        pos.play(color, moves[i]);
        if (moves[i]) numbers.set(moves[i], i + 1);
        color = color === "B" ? "W" : "B";
      }
      view = { position: pos, numbers, last: moves[state.step - 1] };
      const t = k.territory?.[state.line];
      lead = t?.lead[state.step - 1];
      territory = t?.own[state.step - 1];
    }
    if (bar.isOn() && state.mode === "answer") {
      view.territory = territory;
      bar.info.replaceChildren(...situation(lead, territory, game.komi));
    }
    draw(svg, view);
    if (state.line !== null) {
      const total = k.lines[state.line].moves.length;
      stepLabel.textContent = state.step === 0 ? `共 ${total} 步` : `第 ${state.step} / ${total} 步`;
      prevBtn.disabled = state.step === 0;
      nextBtn.disabled = state.step >= total;
    } else {
      stepLabel.textContent = "选一个变化看看";
      prevBtn.disabled = nextBtn.disabled = true;
    }
    lineBtns.forEach((b, i) => b.classList.toggle("active", i === state.line));
    resetBtn.disabled = state.line === null;
  }

  function reset() {
    state.line = null;
    state.step = 0;
    render();
  }
  function selectLine(i) {
    if (state.line !== i) state.step = 1;
    state.line = i;
    render();
  }
  function step(d) {
    if (state.line === null) return;
    const total = k.lines[state.line].moves.length;
    state.step = Math.max(0, Math.min(total, state.step + d));
    render();
  }
  prevBtn.addEventListener("click", () => step(-1));
  nextBtn.addEventListener("click", () => step(1));

  let touchX = null;
  svg.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; }, { passive: true });
  svg.addEventListener("touchend", (e) => {
    if (touchX === null || state.mode !== "answer") return;
    const dx = e.changedTouches[0].clientX - touchX;
    touchX = null;
    if (Math.abs(dx) > 40) step(dx < 0 ? 1 : -1);
  });

  const rec = k.recommended?.move;
  const best = k.marks.find((m) => m.role === "ai_best")?.point;
  // Points the pipeline rated about as good as A (fact close_alternatives): also right answers.
  const alikeLabels = (k.facts || []).find((f) => f.type === "close_alternatives")?.marks || [];
  const alike = new Map((k.candidates || []).filter((c) => alikeLabels.includes(c.label)).map((c) => [c.point, c.label]));
  const summary = h("summary", {}, "看答案");
  const details = h("details", { class: "answer" },
    summary,
    h("div", { class: "answer-body" },
      feedback,
      h("h4", {}, "发生了什么"),
      h("ul", { class: "facts" }, k.explain.template.map((s) => h("li", {}, richText(s)))),
      candidateTable(k.candidates),
      k.explain.tip ? h("p", { class: "tip" }, h("b", {}, "下次先看："), k.explain.tip) : null));

  details.addEventListener("toggle", () => {
    state.mode = details.open ? "answer" : "question";
    summary.textContent = details.open ? "收起答案" : "看答案";
    controls.hidden = !details.open;
    if (!details.open) { state.line = null; state.step = 0; }
    render();
  });

  svg.addEventListener("click", (e) => {
    if (state.mode !== "question") return;
    const p = pointFromEvent(svg, e, game.board);
    if (!p || base.stones.has(p)) return;
    state.guess = p;
    const near = (a, b) => {
      if (!a || !b) return false;
      return Math.max(Math.abs(a.charCodeAt(0) - b.charCodeAt(0)), Math.abs(a.charCodeAt(1) - b.charCodeAt(1))) <= 1;
    };
    let msg, result = "wrong";
    if (k.kind === "good") {
      if (p === k.played) { msg = "对了！就是这一手。"; result = "right"; }
      else msg = "你选了 ◯。看看实战下的 A 好在哪里。";
    } else if (p === rec || p === best) { msg = "答对了！和推荐的下法一样。"; result = "right"; }
    else if (alike.has(p)) { msg = `答对了！${alike.get(p)} 和 A 差不多一样好。`; result = "right"; }
    else if (p === k.played) msg = "你选的和实战一样（✕），看看哪里有问题。";
    else if (near(p, rec)) { msg = "很接近了！推荐的是旁边的 A。"; result = "close"; }
    else msg = "你选了 ◯，对比一下推荐的 A。";
    feedback.replaceChildren(...richText(msg));
    feedback.hidden = false;
    details.open = true;
    opts.onGuess?.(result);
  });

  render();
  const kind = KIND[k.kind] || KIND.mistake;
  const toMove = COLOR_ZH[game.moves[k.position.moveIndex][0]];
  const card = h("article", { class: `card ${k.kind}`, id: opts.id ?? k.id },
    h("header", {},
      h("span", { class: `kind ${k.kind}` }, `${kind.icon} ${kind.label}`),
      h("h3", {}, opts.heading ?? `第 ${k.move} 手：`, richText(k.title))),
    h("div", { class: "card-body" },
      h("div", { class: "board-wrap" }, svg, controls),
      h("div", { class: "text" },
        h("p", { class: "question" },
          k.kind === "good" ? `轮到你下（${toMove}），这里有一手好棋，你能找到吗？` : `轮到你下（${toMove}），你会下哪里？`),
        h("p", { class: "hint" }, "可以直接点棋盘猜一猜，再看答案。"),
        details)));
  // Deep link (game.html?id=..&open=k1&line=0&step=3): opens the answer at a variation step.
  card.showSituation = bar.set;
  card.openAt = (line, stepNo) => {
    details.open = true;
    state.mode = "answer";
    controls.hidden = false;
    if (line != null && k.lines[line]) { state.line = line; state.step = Math.min(stepNo ?? 1, k.lines[line].moves.length); }
    render();
  };
  return card;
}

