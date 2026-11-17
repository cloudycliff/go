// Game list: data/index.json, newest first.

const OUTCOME = { win: "胜", lose: "负", draw: "和", unknown: "" };

function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null) node.append(c);
  return node;
}

// A link to "我的常见问题" above the list, once the statistics exist.
async function habitsLink(list) {
  try {
    const res = await fetch("data/habits.json", { cache: "no-cache" });
    if (!res.ok) return;
    const data = await res.json();
    if (!data.habits?.length) return;
    list.before(h("a", { class: "habits-link", href: "habits.html" },
      h("span", {}, "我的常见问题", h("br"), h("span", { class: "small" }, `最近 ${data.games} 盘棋里最常见的 ${data.habits.length} 件事`)),
      h("span", {}, "›")));
  } catch { /* no link */ }
}

async function main() {
  const root = document.getElementById("list");
  let games;
  try {
    const res = await fetch("data/index.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(res.status);
    games = await res.json();
  } catch {
    root.textContent = "还没有复盘。";
    return;
  }
  if (!games.length) { root.textContent = "还没有复盘。"; return; }
  habitsLink(root);
  root.replaceChildren(...games.map((g) =>
    h("a", { class: `game-card ${g.result}`, href: `game.html?id=${encodeURIComponent(g.id)}` },
      h("div", { class: "row" },
        h("span", { class: "date" }, g.date),
        h("b", { class: `outcome ${g.result}` }, OUTCOME[g.result] || "")),
      h("div", { class: "who" },
        h("span", { class: `stone-dot ${g.color === "B" ? "black" : "white"}` }),
        `执${g.color === "B" ? "黑" : "白"} 对 ${g.opponent}（${g.opponentRank}）`),
      h("p", { class: "sum" }, g.summary),
      h("div", { class: "row small" },
        h("span", {}, `${g.moveCount} 手 · ${g.resultText}`),
        h("span", {}, `${g.keyPointCount} 个关键点 ›`)))));
}

main();
