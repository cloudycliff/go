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

function phaseBars(phases) {
  const max = Math.max(1, ...phases.flatMap((p) => [p.rate, p.opponentRate]));
  return h("div", { class: "phase-bars" }, phases.map((p) =>
    h("div", { class: "phase-row" },
      h("span", { class: "phase-name" }, PHASE_ZH[p.phase] || p.phase),
      h("div", { class: "bars" },
        h("div", { class: "bar me", style: `width:${(100 * p.rate) / max}%` }),
        h("div", { class: "bar them", style: `width:${(100 * p.opponentRate) / max}%` })),
      h("span", { class: "phase-num" }, `${Math.round(p.rate)} / ${Math.round(p.opponentRate)}`))));
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
      `最近 ${habit.games} 盘里出现过。你下亏的棋里，大约每 10 手有 ${Math.max(1, times)} 手是这样；` +
      `和你水平差不多的对手，大约 ${Math.max(0, Math.round(habit.opponentShare * 10))} 手。`),
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
  const better = data.rate <= data.opponentRate;
  root.replaceChildren(
    h("a", { href: "./", class: "back" }, "‹ 全部对局"),
    h("h1", {}, "我的常见问题"),
    h("p", { class: "meta" }, `根据最近 ${data.games} 盘棋（${data.from} 至 ${data.to}）里的每一手统计。`),
    h("section", { class: "chart overview" },
      h("h2", {}, better ? "总的来说，你和对手下得差不多好" : "总的来说，你比对手多亏了一些"),
      h("p", {}, `每 100 手棋里，你大约有 ${Math.round(data.rate)} 手下亏得比较多，` +
        `和你水平差不多的对手大约 ${Math.round(data.opponentRate)} 手。`),
      phaseBars(data.phases),
      h("p", { class: "legend" },
        h("span", { class: "swatch me" }), "你　", h("span", { class: "swatch them" }), "对手　（每 100 手里下亏的手数，胜负已定以后的不算）")),
    sections.length
      ? h("p", { class: "lead-in" }, "下面这几件事，你比对手更常出问题。每次下棋前想一想，就能少亏很多。")
      : h("p", {}, "最近没有比对手更常出现的问题，继续保持！"),
    ...sections,
    h("p", { class: "hint" }, "这些是程序自动统计的，仅供参考。"));
  if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
}

main();
