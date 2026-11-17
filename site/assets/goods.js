// 好棋集锦: every good move of the published games, newest first, as cards to find again.

import { h, keyPointCard } from "./card.js";

async function fetchJson(url) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(res.status);
  return res.json();
}

async function main() {
  const root = document.getElementById("app");
  let data;
  try {
    data = await fetchJson("data/practice.json");
  } catch {
    root.replaceChildren(h("a", { href: "./", class: "back" }, "‹ 全部对局"), h("p", {}, "还没有好棋。"));
    return;
  }
  const goods = data.questions.filter((q) => q.kind === "good");
  const list = h("div", { class: "goods" });
  root.replaceChildren(
    h("a", { href: "./", class: "back" }, "‹ 全部对局"),
    h("h1", {}, "好棋集锦"),
    h("p", { class: "meta" },
      goods.length
        ? `你一共下出了 ${goods.length} 手好棋：AI 最喜欢的一手，和你水平差不多的人很少能找到。再找一次，看看还记不记得。`
        : "还没有好棋，继续加油！"),
    list);
  // Load the games one after another so the first cards show up quickly.
  const pages = new Map();
  for (const q of goods) {
    let page = pages.get(q.game);
    if (!page) {
      try { page = await fetchJson(`data/games/${q.game}.json`); } catch { continue; }
      pages.set(q.game, page);
    }
    const k = page.keyPoints.find((x) => x.id === q.keyPoint);
    if (!k) continue;
    const card = keyPointCard(page, k, { id: `g-${q.game}-${q.keyPoint}`, heading: `${q.date} 第 ${q.move} 手：` });
    card.querySelector("header").append(
      h("a", { href: `game.html?id=${encodeURIComponent(q.game)}&open=${q.keyPoint}` }, "看整盘 ›"));
    list.append(card);
  }
}

main();
