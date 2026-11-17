// "我的常见问题": habits found across recent games, each with examples from published key points.
// data/habits.json is written by `python -m pipeline stats`; it holds counts only. The example
// boards come from the published game pages, so games kept on the computer never show here.

import { h, keyPointCard } from "./card.js";

const PHASE_ZH = { opening: "布局", middle: "中盘", endgame: "官子" };

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(res.status);
  return res.json();
}

// "每 N 手有 1 手坏棋" reads easier for a child than "N 手 / 100 手".
function everyN(rate) {
  return rate > 0 ? Math.max(1, Math.round(100 / rate)) : null;
}

function everyText(rate) {
  const n = everyN(rate);
  if (n === null) return "几乎没有坏棋";
  return n === 1 ? "几乎每手都是坏棋" : `每 ${n} 手有 1 手坏棋`;
}

// Compared with the opponents: small differences are noise, so they count as the same.
function compare(rate, opponentRate) {
  if (Math.abs(rate - opponentRate) < 1 || Math.abs(rate - opponentRate) < 0.15 * opponentRate) return "和对手差不多";
  return rate < opponentRate ? "比对手好一点" : "比对手多一些";
}

// One plain sentence per phase: how often a bad move comes, and how that compares.
function phaseLines(phases) {
  const worst = phases.reduce((a, b) => (b.rate > a.rate ? b : a));
  const best = phases.reduce((a, b) => (b.rate < a.rate ? b : a));
  return h("ul", { class: "phase-lines" }, phases.map((p) => {
    const note = p === best ? "最稳" : p === worst ? "最容易出错" : "";
    return h("li", {},
      h("b", {}, PHASE_ZH[p.phase] || p.phase), note ? `（${note}）` : "", "：",
      `${everyText(p.rate)}，${compare(p.rate, p.opponentRate)}（对手${everyText(p.opponentRate)}）。`);
  }));
}

async function habitSection(habit, n, pages) {
  const examples = [];
  for (const ex of habit.examples) {
    const data = pages.get(ex.game);
    const k = data?.keyPoints.find((x) => x.id === ex.keyPoint);
    if (!k) continue;
    const link = h("a", { href: `game.html?id=${encodeURIComponent(ex.game)}&open=${ex.keyPoint}` }, "看整盘 ›");
    const card = keyPointCard(data, k, { id: `h${n}-${ex.keyPoint}-${ex.game}`, heading: `${ex.date} 第 ${k.move} 手：` });
    card.querySelector("header").append(link);
    examples.push(card);
  }
  const times = Math.round(habit.share * 10);
  return h("section", { class: "habit" },
    h("h2", {}, `${n}. ${habit.title}`),
    h("p", {}, habit.text),
    h("p", { class: "habit-count" },
      `最近 ${habit.games} 盘里都出现过。你的坏棋里，每 10 手大约有 ${Math.max(1, times)} 手是这种；` +
      `对手的坏棋里，只有大约 ${Math.max(0, Math.round(habit.opponentShare * 10))} 手。`),
    h("p", { class: "tip" }, h("b", {}, "下次先看："), habit.tip),
    examples.length ? h("h3", { class: "examples-head" }, "从你的棋里找的例子") : null,
    examples);
}

async function main() {
  const root = document.getElementById("app");
  let data;
  try {
    data = await fetchJson("data/habits.json");
  } catch {
    root.replaceChildren(h("a", { href: "./", class: "back" }, "‹ 全部对局"), h("p", {}, "还没有统计。"));
    return;
  }
  const ids = [...new Set(data.habits.flatMap((x) => x.examples.map((e) => e.game)))];
  const pages = new Map();
  await Promise.all(ids.map(async (id) => {
    try { pages.set(id, await fetchJson(`data/games/${id}.json`)); } catch { /* example skipped */ }
  }));
  const sections = [];
  for (const [i, habit] of data.habits.entries()) sections.push(await habitSection(habit, i + 1, pages));
  const overall = compare(data.rate, data.opponentRate);
  root.replaceChildren(
    h("a", { href: "./", class: "back" }, "‹ 全部对局"),
    h("h1", {}, "我的常见问题"),
    h("p", { class: "meta" }, `根据最近 ${data.games} 盘棋（${data.from} 至 ${data.to}）里的每一手统计。`),
    h("section", { class: "chart overview" },
      h("h2", {}, overall === "比对手多一些" ? "总的来说，你比对手多亏了一些" : "总的来说，你和对手下得差不多好"),
      h("p", {}, "AI 把你下的每一手棋都看了一遍，挑出亏得比较多的棋，我们叫它“坏棋”。"),
      h("p", {}, `你平均${everyText(data.rate)}；和你水平差不多的对手，${everyText(data.opponentRate)}。`),
      h("p", {}, "分开看一盘棋的三个阶段："),
      phaseLines(data.phases),
      h("p", { class: "legend" }, "输赢已经很明显以后下的棋，大家都下得随便，不算在里面。")),
    sections.length
      ? h("p", { class: "lead-in" }, "下面这几件事，你比对手更常出问题。每次下棋前想一想，就能少亏很多。")
      : h("p", {}, "最近没有比对手更常出现的问题，继续保持！"),
    ...sections,
    h("p", { class: "hint" }, "这些是程序自动统计的，仅供参考。"));
  if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
}

main();
