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
