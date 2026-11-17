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

// Links to the pages across games (常见问题, 做题, 好棋集锦), once their data is published.
async function toolLinks(list) {
  const get = async (url) => {
    try {
      const res = await fetch(url, { cache: "no-cache" });
      return res.ok ? await res.json() : null;
    } catch { return null; }
  };
  const [habits, practice] = await Promise.all([get("data/habits.json"), get("data/practice.json")]);
  const tiles = [];
  const tile = (href, title, sub) => h("a", { class: "tool", href },
    h("span", {}, h("b", {}, title), h("br"), h("span", { class: "small" }, sub)), h("span", { class: "go" }, "›"));
  if (habits?.habits?.length) tiles.push(tile("habits.html", "我的常见问题", `最近 ${habits.games} 盘棋里最常见的 ${habits.habits.length} 件事`));
  const questions = practice?.questions || [];
  if (questions.length) tiles.push(tile("practice.html", "做题练习", `${questions.length} 道题，都来自你自己的棋`));
  const goods = questions.filter((q) => q.kind === "good").length;
  if (goods) tiles.push(tile("goods.html", "好棋集锦", `你下出的 ${goods} 手好棋`));
  if (tiles.length) list.before(h("nav", { class: "tools" }, tiles));
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
  toolLinks(root);
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
