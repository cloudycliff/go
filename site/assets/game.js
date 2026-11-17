// Single-game review page: game.html?id=<chessid>

import { COLOR_ZH, h, keyPointCard, replayBoard } from "./card.js";
import { drawCurve } from "./chart.js";

const OUTCOME = { win: "胜", lose: "负", draw: "和", unknown: "" };

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

  const replay = replayBoard(data);
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
    replay,
    h("section", { class: "cards" },
      h("h2", {}, data.smallGame ? "这盘下得不错，有两处可以更好" : `关键点（${data.keyPoints.length} 个）`),
      data.keyPoints.map((k) => keyPointCard(data, k))),
    h("footer", { class: "summary" }, h("p", {}, data.summary)));

  // Deep link: &move=N shows move N on the whole-game board; &situation=1 turns 形势 on.
  const params = new URLSearchParams(location.search);
  if (params.has("move")) replay.goTo(Number(params.get("move")));
  const target = params.get("open") && document.getElementById(params.get("open"));
  if (params.get("situation") === "1") {
    replay.showSituation(true);
    target?.showSituation?.(true);
  }
  if (target?.openAt) {
    const line = params.has("line") ? Number(params.get("line")) : null;
    target.openAt(line, params.has("step") ? Number(params.get("step")) : null);
    if (!params.has("noscroll")) target.scrollIntoView({ block: "start" });
  }
}

main();
