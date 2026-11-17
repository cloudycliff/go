// 做题练习: key points of all published games as questions, in sets of 10.
// What the child got right or wrong stays in this browser (localStorage): a question answered
// wrong comes back the next day, one answered right comes back after longer and longer breaks.

import { h, keyPointCard } from "./card.js";

const SET_SIZE = 10;
const DAY = 24 * 3600 * 1000;
const INTERVALS = [1, 3, 7, 14, 30]; // days until a question comes back, by how often it was right in a row
const STORE = "practice:v1";

function load() {
  try { return JSON.parse(localStorage.getItem(STORE) || "{}"); } catch { return {}; }
}

function save(records) {
  try { localStorage.setItem(STORE, JSON.stringify(records)); } catch { /* private mode: not kept */ }
}

const qid = (q) => `${q.game}:${q.keyPoint}`;

// result: "right" / "close" / "wrong" / "peeked" (opened the answer without guessing)
function record(records, q, result, now = Date.now()) {
  const r = records[qid(q)] || { box: 0, right: 0, wrong: 0 };
  if (result === "right") {
    r.right += 1;
    r.box = Math.min(r.box + 1, INTERVALS.length - 1);
    r.due = now + INTERVALS[r.box] * DAY; // first right answer: back in 3 days, then 7, 14, 30
  } else {
    if (result !== "close") r.wrong += 1;
    if (result !== "close") r.box = 0;
    r.due = now + DAY;
  }
  records[qid(q)] = r;
  save(records);
}

function shuffle(list) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// Due reviews first (longest overdue first), then questions never seen, in random order.
function nextSet(questions, records, now = Date.now()) {
  const due = questions.filter((q) => records[qid(q)] && records[qid(q)].due <= now)
    .sort((a, b) => records[qid(a)].due - records[qid(b)].due);
  const fresh = shuffle(questions.filter((q) => !records[qid(q)]));
  return [...due, ...fresh].slice(0, SET_SIZE);
}

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(res.status);
  return res.json();
}

const games = new Map();
async function gameData(id) {
  if (!games.has(id)) games.set(id, fetchJson(`data/games/${id}.json`));
  return games.get(id);
}

async function main() {
  const root = document.getElementById("app");
  let data;
  try {
    data = await fetchJson("data/practice.json");
  } catch {
    root.replaceChildren(h("a", { href: "./", class: "back" }, "‹ 全部对局"), h("p", {}, "还没有题目。"));
    return;
  }
  const records = load();
  const filters = [{ key: "all", title: "全部题目", test: () => true }];
  for (const habit of data.habits) {
    const n = data.questions.filter((q) => q.habits.includes(habit.key)).length;
    if (n) filters.push({ key: habit.key, title: habit.title, test: (q) => q.habits.includes(habit.key) });
  }
  filters.push({ key: "good", title: "找好棋", test: (q) => q.kind === "good" });
  let filter = filters[0];

  const chips = h("div", { class: "chips" });
  const status = h("p", { class: "meta" });
  const stage = h("div", { class: "stage" });
  root.replaceChildren(
    h("a", { href: "./", class: "back" }, "‹ 全部对局"),
    h("h1", {}, "做题练习"),
    h("p", { class: "meta" }, "题目都来自你自己下过的棋。每组 10 题，先在棋盘上点一下你想下的地方，再看答案。"),
    chips, status, stage);

  function drawChips() {
    chips.replaceChildren(...filters.map((f) => {
      const n = data.questions.filter(f.test).length;
      const b = h("button", { type: "button", class: f === filter ? "chip active" : "chip" }, `${f.title}（${n}）`);
      b.addEventListener("click", () => { filter = f; drawChips(); startSet(); });
      return b;
    }));
  }

  function drawStatus() {
    const list = data.questions.filter(filter.test);
    const seen = list.filter((q) => records[qid(q)]);
    const mastered = seen.filter((q) => records[qid(q)].box >= 2).length;
    const due = seen.filter((q) => records[qid(q)].due <= Date.now()).length;
    status.textContent = `这一类共 ${list.length} 道：做过 ${seen.length} 道，已经掌握 ${mastered} 道` +
      (due ? `，今天有 ${due} 道要复习。` : "。");
  }

  function startSet() {
    drawStatus();
    const set = nextSet(data.questions.filter(filter.test), records);
    if (!set.length) {
      stage.replaceChildren(h("section", { class: "chart done" },
        h("h2", {}, "这一类的题目都做完了！"),
        h("p", {}, "答错的题明天会再出现，答对的过几天再来复习。也可以换一类题目试试。")));
      return;
    }
    let i = 0, right = 0;
    const show = async () => {
      if (i >= set.length) {
        drawStatus();
        const again = h("button", { type: "button", class: "primary" }, "再来一组");
        again.addEventListener("click", startSet);
        stage.replaceChildren(h("section", { class: "chart done" },
          h("h2", {}, `这一组答对了 ${right} / ${set.length} 题`),
          h("p", {}, right === set.length ? "全对，太棒了！" : "答错的题明天会再出现，再看一次就记住了。"),
          again));
        return;
      }
      const q = set[i];
      stage.replaceChildren(h("p", { class: "meta" }, "加载中……"));
      let page;
      try { page = await gameData(q.game); } catch { i += 1; show(); return; }
      const k = page.keyPoints.find((x) => x.id === q.keyPoint);
      if (!k) { i += 1; show(); return; }
      let result = null;
      const card = keyPointCard(page, k, {
        id: `q-${q.game}-${q.keyPoint}`,
        heading: `${q.date} 第 ${q.move} 手：`,
        onGuess: (r) => { if (result === null) result = r; },
      });
      const link = h("a", { href: `game.html?id=${encodeURIComponent(q.game)}&open=${q.keyPoint}` }, "看整盘 ›");
      card.querySelector("header").append(link);
      const next = h("button", { type: "button", class: "primary" }, i + 1 < set.length ? "下一题 ›" : "看成绩 ›");
      next.addEventListener("click", () => {
        const peeked = card.querySelector("details")?.open;
        const r = result ?? (peeked ? "peeked" : null);
        if (r) record(records, q, r);
        if (r === "right") right += 1;
        i += 1;
        show();
        stage.scrollIntoView({ block: "start" });
      });
      stage.replaceChildren(
        h("p", { class: "progress" }, `第 ${i + 1} / ${set.length} 题 · 已答对 ${right} 题`),
        card,
        h("div", { class: "next-row" }, next));
    };
    show();
  }

  drawChips();
  startSet();
}

main();
