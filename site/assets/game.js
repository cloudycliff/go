// Single-game review page: game.html?id=<chessid>

import { draw, pointFromEvent, positionAt } from "./board.js";
import { drawCurve } from "./chart.js";

const KIND = {
  mistake: { label: "错误", icon: "✗" },
  missed_punish: { label: "没惩罚对方", icon: "!" },
  missed_urgent: { label: "漏掉急所", icon: "!" },
  good: { label: "好棋", icon: "★" },
};
const OUTCOME = { win: "胜", lose: "负", draw: "和", unknown: "" };
const COLOR_ZH = { B: "黑", W: "白" };

function h(tag, attrs, ...children) {
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
function richText(text) {
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
function candidateTable(list) {
  const rows = (list || []).filter((c) => c.label && c.diff != null);
  if (rows.length < 2) return null;
  return h("table", { class: "cands" },
    h("thead", {}, h("tr", {}, h("th", {}, "下在"), h("th", {}, "比最好的差"), h("th", {}, "说明"))),
    h("tbody", {}, rows.map((c) => h("tr", { class: c.role === "played" ? "played" : "" },
      h("td", {}, richText(c.label)),
      h("td", {}, c.first ? "最好" : c.diff < 0.5 ? "差不多" : `约 ${Math.round(c.diff)} 目`),
      h("td", {}, c.note || "")))));
}

function keyPointCard(game, k) {
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
  const lineBtns = k.lines.map((line, i) =>
    h("button", { class: "line", type: "button", onclick: () => selectLine(i) }, line.name));
  const controls = h("div", { class: "controls", hidden: "" },
    h("div", { class: "lines" }, lineBtns),
    h("div", { class: "stepper" }, prevBtn, stepLabel, nextBtn));
  const feedback = h("p", { class: "feedback", hidden: "" });

  function render() {
    let view;
    if (state.mode === "question") {
      view = { position: base, last: prevMove?.[1], guess: state.guess };
    } else if (state.line === null || state.step === 0) {
      view = { position: base, last: prevMove?.[1], marks: k.marks, guess: state.guess };
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
  const summary = h("summary", {}, "看答案");
  const details = h("details", { class: "answer" },
    summary,
    h("div", { class: "answer-body" },
      feedback,
      h("h4", {}, "发生了什么"),
      h("ul", { class: "facts" }, k.explain.template.map((s) => h("li", {}, richText(s)))),
      candidateTable(k.candidates),
      k.explain.tip ? h("p", { class: "tip" }, h("b", {}, "下次先看："), k.explain.tip) : null,
      k.explain.llm?.verified ? h("div", { class: "llm" },
        h("h4", {}, "AI 老师说 ", h("span", { class: "badge-ref" }, "仅供参考")),
        k.explain.llm.sentences.map((s) => h("p", {}, richText(s.text))),
        k.explain.llm.tip ? h("p", { class: "tip" }, richText(k.explain.llm.tip.text)) : null) : null));

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
    let msg;
    if (k.kind === "good") msg = p === k.played ? "对了！就是这一手。" : "你选了 ◯。看看实战下的 A 好在哪里。";
    else if (p === rec || p === best) msg = "答对了！和推荐的下法一样。";
    else if (p === k.played) msg = "你选的和实战一样（✕），看看哪里有问题。";
    else if (near(p, rec)) msg = "很接近了！推荐的是旁边的 A。";
    else msg = "你选了 ◯，对比一下推荐的 A。";
    feedback.replaceChildren(...richText(msg));
    feedback.hidden = false;
    details.open = true;
  });

  render();
  const kind = KIND[k.kind] || KIND.mistake;
  const toMove = COLOR_ZH[game.moves[k.position.moveIndex][0]];
  const card = h("article", { class: `card ${k.kind}`, id: k.id },
    h("header", {},
      h("span", { class: `kind ${k.kind}` }, `${kind.icon} ${kind.label}`),
      h("h3", {}, `第 ${k.move} 手：`, richText(k.title))),
    h("div", { class: "card-body" },
      h("div", { class: "board-wrap" }, svg, controls),
      h("div", { class: "text" },
        h("p", { class: "question" },
          k.kind === "good" ? `轮到你下（${toMove}），这里有一手好棋，你能找到吗？` : `轮到你下（${toMove}），你会下哪里？`),
        h("p", { class: "hint" }, "可以直接点棋盘猜一猜，再看答案。"),
        details)));
  // Deep link (game.html?id=..&open=k1&line=0&step=3): opens the answer at a variation step.
  card.openAt = (line, stepNo) => {
    details.open = true;
    state.mode = "answer";
    controls.hidden = false;
    if (line != null && k.lines[line]) { state.line = line; state.step = Math.min(stepNo ?? 1, k.lines[line].moves.length); }
    render();
  };
  return card;
}

async function main() {
  const id = new URLSearchParams(location.search).get("id");
  const root = document.getElementById("app");
  if (!id || !/^[\w-]+$/.test(id)) { root.textContent = "没有指定棋局。"; return; }
  let data;
  try {
    const res = await fetch(`data/games/${id}.json`);
    if (!res.ok) throw new Error(res.status);
    data = await res.json();
  } catch {
    root.textContent = "找不到这盘棋的复盘。";
    return;
  }
  const g = data.game;
  const me = g.studentColor;
  const opp = g.opponent;
  document.title = `复盘 ${g.date} 对 ${opp.name}`;
  const curve = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  curve.setAttribute("class", "curve");
  drawCurve(curve, data.curve, data.keyPoints, (k) => {
    document.getElementById(k.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  root.replaceChildren(
    h("header", { class: "game-head" },
      h("a", { href: "./", class: "back" }, "‹ 全部对局"),
      h("h1", {}, `${g.date} 对 ${opp.name}`),
      h("p", { class: "meta" },
        `你执${COLOR_ZH[me]}（${(me === "B" ? g.black : g.white).rank}），对手 ${opp.rank}，`,
        h("b", { class: `outcome ${g.outcome}` }, OUTCOME[g.outcome] || ""), ` ${g.result}，共 ${g.moves.length} 手`,
        g.handicap ? `，让 ${g.handicap} 子` : "")),
    h("section", { class: "chart" },
      h("h2", {}, "目差曲线"),
      h("p", { class: "legend" }, "线在上面：你领先；在下面：对方领先。点圆点看关键点。"),
      curve),
    h("section", { class: "cards" },
      h("h2", {}, data.smallGame ? "这盘下得不错，有两处可以更好" : `关键点（${data.keyPoints.length} 个）`),
      data.keyPoints.map((k) => keyPointCard(g, k))),
    h("footer", { class: "summary" }, h("p", {}, data.summary)));

  const params = new URLSearchParams(location.search);
  const target = params.get("open") && document.getElementById(params.get("open"));
  if (target?.openAt) {
    const line = params.has("line") ? Number(params.get("line")) : null;
    target.openAt(line, params.has("step") ? Number(params.get("step")) : null);
    if (!params.has("noscroll")) target.scrollIntoView({ block: "start" });
  }
}

main();
