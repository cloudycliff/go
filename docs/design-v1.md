# 野狐对局复盘系统 v1 设计

状态：草案（2026-11-16）
读者：家长（开发者）。最终用户：孩子（10 岁，野狐 8 级，现实业余 1 级；用 iPad / 笔记本查看）。

## 1. 目标与边界

**v1 要做到：** 拉取孩子最近的野狐公开对局 → 家长选一局 → 本机 KataGo 分析 → 自动挑出 3～5 个
关键点（错误 + 错过的机会 + 1 个好棋）→ 生成静态页面数据 → 推送 GitHub → Cloudflare Pages
发布 → 孩子在 iPad 上打开学习。

**v1 不做：** 登录、试下、在线分析、多盘统计（但数据为它预留字段）。

**三条设计原则：**

1. **事实由程序算，话由 LLM 说。** 页面上的数字、位置、"能吃几颗子"都来自 KataGo 数据和棋盘
   回放；LLM 只负责把这些事实讲成孩子听得懂的话，并标注"仅供参考"。家长不具备审核 LLM 的能力，
   所以 LLM 输出必须由程序校验，校验不过就退回模板讲解。
2. **按 8 级的水平判断和建议。** 判错用按段位折算的胜率，推荐优先给"高一两档的人会下的棋"。
3. **原始分析只跑一次。** 每手的 KataGo 原始结果永久保存，以后改算法、加多盘统计都不用重跑引擎。

## 2. 总体结构

```
go-review/
├── config.toml              # 昵称、KataGo 路径、分析参数（不含密钥）
├── pipeline/                # 本地 CLI（Python 3.11+）
│   ├── cli.py               # review list / analyze / publish
│   ├── fox.py               # 野狐：昵称→UID→棋谱列表→SGF
│   ├── sgf.py               # SGF 解析：规则、贴目、让子、双方段位
│   ├── katago.py            # katago analysis 进程（JSON 行协议）
│   ├── analyze.py           # 两阶段分析，写 raw/
│   ├── evaluate.py          # 每手损失、按段位折算胜率
│   ├── keypoints.py         # 关键点候选、合并成片段、挑选
│   ├── facts.py             # 回放变化、提子、气、归属变化 → 事实列表
│   ├── narrate_template.py  # 模板讲解（兜底）
│   ├── narrate_llm.py       # LLM 讲解
│   ├── verify.py            # LLM 输出校验
│   └── publish.py           # 写 site/data、更新索引、git commit/push
├── raw/                     # 每局原始分析（入库，不发布）
│   └── <chessid>.json.gz
└── site/                    # Cloudflare Pages 输出目录（纯静态）
    ├── index.html           # 棋局列表
    ├── game.html            # 单局复盘查看器（?id=<chessid>）
    ├── assets/{app.js, board.js, chart.js, style.css}
    ├── robots.txt           # Disallow: /
    └── data/
        ├── index.json       # 棋局索引
        └── games/<chessid>.json
```

Cloudflare Pages 绑定 GitHub 仓库，构建命令留空，输出目录为 `site/`，不需要构建步骤。

**环境前提：**

- 本机目前没有 Python（之前调用时提示 "Python was not found"），需要安装 Python 3.11+。
- KataGo 直接用发行版：
  `C:\src\go\LizzieYzy Next NVIDIA\app\engines\katago\windows-x64\katago.exe`（v1.18.2，CUDA）
  和 `app\weights\default.bin.gz`（B11 transformer）。
- 另需下载 HumanSL 模型（KataGo 官方 release 的 `b18c384nbt-humanv0.bin.gz`，约 100MB），按 SHA-256 校验。
- LLM 的 API Key 只放环境变量，绝不写进仓库。

## 3. 流程与命令

```
review list                         # 拉最近 20 局：日期、对手及段位、执色、胜负、手数、chessid
review analyze <chessid>            # 抓 SGF → 分析 → 关键点 → 讲解 → 写 raw/ 与 site/data/
review analyze --sgf a.sgf          # 野狐接口失效时的手动导入
review publish                      # git add/commit/push → Cloudflare 自动发布
review analyze --latest --publish   # 一条命令做完（以后挂定时任务用）
```

### 3.1 拉取对局（fox.py）

参考 LizzieYzy `GetFoxRequest`，分三步：

1. 用 `newframe.foxwq.com/cgi/QueryUserInfoPanel` 把昵称换成 UID；
2. 用 `h5.foxwq.com/yehuDiamond/chessbook_local` 取棋谱列表；
3. 按 chessid 下载 SGF。

这是非官方接口，随时可能失效。处理原则：低频调用、带超时；失败时给出明确提示，引导改用 `--sgf`；
列表结果缓存到本地。

过滤：只取 19 路（野狐的 11 路是特殊玩法，不复盘）。让子棋保留，读取 `HA`/`AB` 传给引擎；
野狐的“让先”（`HA[1]`，贴目 0）按普通对局分析，贴目传 0。

### 3.2 两阶段分析（analyze.py）

规则、贴目从 SGF 读取并传给 KataGo，避免胜率系统性偏差。

| 阶段 | 对象 | 参数 | 用途 |
|---|---|---|---|
| 1 全盘 | 每个局面 | 400 visits，`includeOwnership`，`includePolicy`，HumanSL `humanSLProfile` = 孩子档位 | 每手损失、目差曲线、候选关键点 |
| 2 精查 | 候选关键点（约 15 个）的"实战前"和"实战后"局面 | 3000 visits，PV 最长 15 手 | 推荐变化、对方惩罚变化、更准的损失 |

耗时估算按本机基准约 815 visits/s：阶段 1 为 250 手 × 400 ≈ 2 分钟；阶段 2 为 30 × 3000 ≈ 2 分钟；
合计一局约 5 分钟。

HumanSL 档位按 LizzieYzy `CoachLevel` 对照表从段位映射：野狐 7-8K 对应 `preaz_11k`。档位每局从
SGF 的段位字段（`BR`/`WR`）读取，孩子升级后自动跟随。"高一档"推荐默认取 `preaz_9k`（可配置）。

### 3.3 每手评价（evaluate.py）

以下都从走棋一方的视角计算：

- **目损**：`scoreLoss` = 首选点的 scoreLead − 实战手的 scoreLead，优先用同一次搜索里实战手的
  候选值。实战手不在候选里，或 visits < max(16, 首选 ÷ 20) 时，改用下一局面根节点的值。负值记为 0。
- **按段位折算胜率**：`p = Φ(scoreLead / σ)`。σ 取 HumanSL 给出的该局面目差标准差，下限 1，
  缺失时取 12（同 LizzieYzy `RankAwareWinrate`）。损失为走前 p 减去走后 p。
- **等级**：沿用 LizzieYzy 的实测阈值。

  | 等级 | 折算胜率损失 | 胜负已定（p < 5% 或 > 95%）时改看目损 |
  |---|---|---|
  | 缓手 | 5% | — |
  | 问题手 | 10% | 10 目 |
  | 恶手 | 20% | 20 目 |

- **同侪概率**：实战手和推荐手在孩子档位 humanPolicy 下的概率，用来判断"这手是不是 8 级常见
  错误"和"推荐手对他是否太难"。

## 4. 关键点挑选（keypoints.py）

> M2 用 3 局真实对局校准后，规则有改动（片段按净损失评级、急所类限 2 个、每阶段上限 3、好棋放宽并用
> probe 实测），以 [progress.md](progress.md) 的"M2 校准决定"为准。

### 4.1 候选类型

| 类型 | 条件 | 讲法 |
|---|---|---|
| `mistake` 错误 | 孩子的手 ≥ 问题手 | 你丢了什么 |
| `missed_punish` 没惩罚 | 对方上一手 ≥ 问题手，且孩子这手又损失 ≥ 对方损失的一半（便宜没拿回来） | 对方给了你机会 |
| `missed_urgent` 共同漏看 | 同一急所（首选点相同或距离 ≤ 2）连续 ≥ 3 个孩子的回合都是首选，且孩子每次都没下 | 这里你有 N 次机会 |
| `good` 好棋 | 孩子下了首选点，该点在孩子档位的同侪概率 < 10%，且同侪常见下法损失 ≥ 5% | 这手下得好 |

### 4.2 合并成片段

同一场战斗里连续出错时，合并为一个片段，只讲一次：

- 合并条件：相邻候选相距 ≤ 6 手，且推荐点或实战点的距离 ≤ 4 路；
- 片段的代表手取损失最大的那一手；片段的损失取各手之和。

### 4.3 选取

1. 按片段的折算损失排序，取前 4 个（错误类和机会类混排）。约束：同一阶段（布局 < 60 手、
   中盘、官子 > 180 手）最多 2 个。
2. 再加 1 个 `good`，没有就不加。
3. 一盘全是小错时，取损失最大的 2 个，标题改为"这盘下得不错，有两处可以更好"。

## 5. 事实提取（facts.py）——讲解的唯一依据

每个关键点产出一组带 ID 的事实，全部由程序计算、可复现：

| 事实类型 | 计算方式 | 示例 |
|---|---|---|
| `loss` | 3.3 的目损和等级 | 亏约 12 目，属于恶手 |
| `refute_capture` | 在棋盘上回放"实战后"局面的 PV（对方最好应法），统计提子 | 对方接下来可以吃掉 ▲ 4 颗子 |
| `best_capture` / `best_save` | 回放推荐 PV，统计提子和救出 | 推荐下法能吃掉 △ 3 颗子 |
| `atari_ignored` | 走前孩子有棋块只剩 1 口气，实战手没有长气、提子或反打 | 你的 ▲ 棋被叫吃了，没有逃 |
| `self_atari` | 实战手之后，己方棋块只剩 1 口气 | 这手让自己只剩一口气 |
| `group_flip` | 按连通块统计 ownership 均值：走前 ≥ 0.6、走后 ≤ −0.3（或反过来） | AI 认为 ▲ 这块棋很可能被吃 |
| `area_flip` | 空点 ownership 翻转的数量和区域 | 右下约 15 个点的地变成对方的 |
| `peer_choice` | 高一档 humanPolicy 的首选点，及其与 AI 首选的目差 | 比你强一点的人多数会下 B 点，和 AI 首选只差 0.5 目 |
| `phase` / `category` | 手数定阶段；归属变化集中在棋子上为"死活/对杀"，在空地上为"大场/实地"，官子阶段的小损失为"官子" | 类别：死活 |

**棋盘标记**：事实里引用的点和棋块统一编号为标记（A/B/C 点、▲/△ 棋块），页面画在棋盘上，
讲解只用标记称呼，**不出现坐标**。孩子不用读坐标，校验也更简单。

**推荐着法**：默认展示 AI 首选。如果 `peer_choice` 与 AI 首选的目差 ≤ 1 目，主推 `peer_choice`，
并注明"AI 最强是 A 点，差别不大"。

## 6. 讲解生成

### 6.1 模板讲解（兜底，总是生成）

按事实类型拼句，例如：

> 你下了 ✕，对方接下来可以吃掉 ▲ 4 颗子，这手亏了约 12 目。更好的是 A 点，先把这几颗子连回家。

### 6.2 LLM 讲解（narrate_llm.py）

**输入**：本关键点的事实列表（JSON，含 ID 和标记）、孩子的年龄和段位、输出要求。
不给原始候选和变化坐标，不给棋盘全图，LLM 无从编造位置。

**提示要点**：

- 对 10 岁孩子说话，第二人称，3～5 句，每句不超过 30 字；
- 只能使用给出的事实，每句必须引用至少一个事实 ID；
- 用标记称呼位置，不写坐标；不出现"胜率 xx%"；不确定就不说；
- 结尾给一个具体的"下次遇到这种情况先看什么"。

**输出格式（JSON）**：

```json
{ "sentences": [ { "text": "你下了✕以后，对方可以吃掉▲这4颗子。", "refs": ["f2"] } ],
  "tip": { "text": "被叫吃时先数一数气，看能不能逃。", "refs": ["f3"] } }
```

### 6.3 校验（verify.py）

不通过时把违规项发回 LLM 重写一次；仍不通过，页面只用模板讲解。

| 检查项 | 规则 |
|---|---|
| 引用 | 每句 `refs` 非空，且 ID 都存在 |
| 标记 | 句中出现的标记都必须在事实里 |
| 坐标 | 出现 `[A-T][1-19]` 形式即违规 |
| 数字 | 句中数字必须等于所引事实中的数字（允许四舍五入）；百分号一律违规 |
| 术语 | "死/活/吃/被吃"需引用 `group_flip` 或 capture 类事实；"劫/征子/定式/先手/后手/双活/眼"v1 一律禁用（这些事实 v1 算不出来） |
| 长度 | 句数、字数在限制内 |

### 6.4 页面上的区分

- **"发生了什么"**：模板和事实，一直显示。
- **"AI 老师说"**：LLM 讲解，带"仅供参考"徽标，样式上与事实区分开。

### 6.5 模型与成本

LLM 接口做成可替换的适配层，具体模型实现时按官方文档确定。用量很小：每局约 5 次调用，每次输入
约 1～2K token、输出约 300 token。

> M3 已定：DeepSeek `deepseek-flash`（OpenAI 兼容接口），关闭思考模式。校验规则在 6.3 的基础上增加了
> "不推测后面的棋""不猜孩子的心态"，并同时检查中文数字。详见 [progress.md](progress.md) 的 M3 部分。

## 7. 数据格式

### 7.1 site/data/games/<chessid>.json

```json
{
  "schemaVersion": 1,
  "game": { "id": "...", "date": "2026-11-15", "board": 19, "komi": 6.5, "rules": "chinese",
            "handicap": 0, "black": {"name": "...", "rank": "8K"}, "white": {"name": "...", "rank": "7K"},
            "studentColor": "B", "result": "W+R", "moves": ["pd", "dp"] },
  "analysis": { "katago": "1.18.2", "model": "b11c768...", "humanProfile": "preaz_11k",
                "visits": [400, 3000], "analyzedAt": "..." },
  "curve": [ { "move": 0, "scoreLead": 0.4 } ],
  "keyPoints": [
    { "id": "k1", "kind": "mistake", "move": 87, "span": [85, 92], "phase": "middle",
      "category": "life_death", "severity": "blunder",
      "scoreLoss": 12.3, "rankAwareLoss": 0.31,
      "position": { "moveIndex": 86 },
      "marks": [ { "label": "▲", "type": "group", "points": ["qd", "qe", "re"] },
                 { "label": "A", "type": "point", "point": "rf" } ],
      "played": "rd",
      "recommended": { "move": "rf", "source": "peer" },
      "lines": [ { "name": "实战后对方的应法", "moves": ["rc", "sd"] },
                 { "name": "推荐下法", "moves": ["rf", "se"] } ],
      "facts": [ { "id": "f1", "type": "loss", "scoreLoss": 12, "severity": "blunder" },
                 { "id": "f2", "type": "refute_capture", "count": 4, "mark": "▲" } ],
      "explain": { "template": ["..."],
                   "llm": { "sentences": [], "tip": {}, "model": "...", "verified": true } } }
  ]
}
```

坐标使用 SGF 格式（`pd`），页面只用它们画图，从不展示给孩子。
`curve.scoreLead` 统一为孩子视角（正数 = 孩子领先）。
`keyPoints[].phase/category/severity/kind/scoreLoss` 是给多盘统计用的字段，v1 就要存齐。

M2 实际输出与上面的差异：`game.moves` 是 `[["B","pd"], ...]`（带颜色，兼容让子和虚手）；另有
`game.setup`（让子摆放）、`game.opponent`、`game.outcome`（`win`/`lose`）；孩子的名字写成"我"。
关键点多了 `title`、`moves`（片段里孩子的各手）、`deep`（是否有深度分析）；`explain` 为
`{template: [...], tip, llm: null}`。顶层多了 `smallGame` 和 `summary`。

### 7.2 site/data/index.json

```json
[ { "id": "...", "date": "...", "opponent": "...", "opponentRank": "7K", "color": "B",
    "result": "lose", "keyPointCount": 5 } ]
```

### 7.3 raw/<chessid>.json.gz

每个局面的 KataGo 原始响应（moveInfos、rootInfo、ownership、humanPolicy），约 0.5～1MB。
只入库，不发布。

## 8. 查看器页面（site/）

- **技术**：原生 HTML/CSS/JS，不用框架；棋盘用 SVG 画，iPad 上清晰；加 `<meta name="robots" content="noindex">`。
- **index.html**：棋局卡片列表，按日期倒序，显示对手、执色、胜负和关键点数。
- **game.html** 自上而下：
  1. **对局信息**：双方、段位、结果。
  2. **目差曲线**：纵轴为孩子领先的目数，不显示胜率；关键点在曲线上标成彩色圆点，点击跳到对应卡片。
  3. **关键点卡片**，每张：
     - 标题：类型图标 + 一句话，如"第 87 手：这块棋可以救"；
     - 棋盘：关键点**之前**的局面，带标记；
     - 提问"轮到你下，你会下哪里？"，用 `<details>` 展开答案；
     - 答案：棋盘显示实战 ✕（红）和推荐 A（绿）；可在"实战后对方的应法 / 推荐下法"两条变化之间
       切换，用上一步 / 下一步按钮翻看；
     - "发生了什么"（事实）和"AI 老师说（仅供参考）"。
  4. **结尾**：这盘的一句话总结，如"2 处死活、1 处没惩罚对方"。
- **布局**：横屏棋盘在左、文字在右；竖屏或窄屏上下排列。按钮 ≥ 44px，变化支持左右滑动。
- **测试**：iPad Safari、Windows Chrome/Edge。

## 9. 隐私

已决定不设登录，站点公开访问。最低限度的处理：

- `robots.txt` 禁止抓取，页面加 noindex，不放真实姓名；
- 仓库可设为私有（Cloudflare Pages 支持私有仓库部署），不影响站点访问。

## 10. 里程碑

| 阶段 | 内容 | 验收 |
|---|---|---|
| M1 | fox.py、sgf.py、katago.py、analyze.py，写出 raw/ | 孩子最近 3 局都能拉取并分析完，曲线与 LizzieYzy 大致一致 |
| M2 | evaluate、keypoints、facts、模板讲解，查看器 v1 | 3 局的关键点让家长看后觉得"确实是大问题"，iPad 上显示正常 |
| M3 | LLM 讲解和校验 | 一组故意违规的输出（坐标、错误数字、禁用术语）全部被拦下；真实输出通过率 ≥ 80% |
| M4 | publish 和 Cloudflare Pages | 一条命令从拉谱到上线 |
| 后续 | 多盘综合分析（找出反复出现的问题）、页面交互（试下）、定时自动分析 | — |

## 11. 待定问题

1. **HumanSL 的 σ**（M1 已确认）：带 `-human-model` 时，`rootInfo.humanScoreStdev` 就是该档位的目差
   标准差。实测 `preaz_11k` 布局约 35 目、中盘 20～30 目、官子 6～8 目，比 LizzieYzy 文档里 3 段
   的 18 目大得多。所以布局阶段亏 10 目，折算胜率也只降约 11%，阈值要在 M2 校准。
   另外，400 visits 下 PV 只有约 5 手，变化图必须依赖阶段 2 的深度分析。
2. **阈值**：问题手 / 恶手阈值，以及 `group_flip` 的 0.6 / −0.3，在 M2 用孩子的真实对局校准。
3. **数量**：每局关键点数量（默认 4 + 1）是否合适，看孩子的实际使用反馈。
4. **LLM 供应商**：待定，适配层可替换。
