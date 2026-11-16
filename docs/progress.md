# 进度与交接

新会话接手时先读这份文件和 [design-v1.md](design-v1.md)。

## 已定的需求（和家长确认过）

- 用户：孩子 10 岁，野狐 8 级（现实业余 1 级），iPad 下棋，用 iPad 和笔记本看复盘。
- 流程：家长本地选局 → KataGo 分析 → 提交到 GitHub（cloudycliff/go）→ Cloudflare Pages 发布 → 孩子在网页上看。
- 按 8 级的水平判错和推荐（HumanSL `preaz_11k`，推荐取高两档 `preaz_9k`）。
- 关键点既讲错误，也讲没抓住的机会，再加一个好棋。
- v1 就接入 LLM 讲解：事实由程序算，LLM 只负责转述，经程序校验，标“仅供参考”。家长无法审核讲解内容。
- 不做登录，数据公开无妨（加 noindex 即可）。
- 只复盘 19 路。11 路是野狐的特殊玩法，不考虑。
- 多盘综合分析留到以后做，但数据格式现在就要预留字段。
- 提交规则：作者为 `cloudycliff <cloudycliff@gmail.com>`；每次修改都提交并推送；不提交敏感信息（`config.toml`）和模型文件（`models/`）。

## 里程碑状态

- [x] M1 拉谱 + 整盘分析：`fox.py`、`sgf.py`、`katago.py`、`analyze.py`、`cli.py`。第 6 局
  （1794223495030021066）实测 219 个局面 87 秒；数据字段已确认（`humanScoreStdev`、`humanPolicy`、ownership）。
- [ ] M2 判错、关键点、事实提取、模板讲解、查看器 v1。
- [ ] M3 LLM 讲解与校验（供应商待定）。
- [ ] M4 一条命令发布到 Cloudflare Pages。

## M1 的实测发现

- 8 级的 `humanScoreStdev` 很大：布局约 35 目，中盘 20～30 目，官子 6～8 目。照搬 LizzieYzy 的
  5% / 10% / 20% 阈值，布局和中盘的错误会判得很宽，M2 要用真实对局校准。
- 400 visits 时 PV 只有约 5 手。变化图需要阶段 2 的 3000 visits 深度分析。
- 野狐接口：`QueryUserInfoPanel`（昵称 → UID）、`YHWQFetchChessList`（最近 100 局）、
  `YHWQFetchChess`（SGF）。可用。旧的 CGI 接口返回 `-3`，不再使用。
- 野狐段位字段 `dan`：17 = 1 级，18 = 1 段，≥100 为职业。约三分之一的对局是让先（`HA[1]`，贴目 0）。

## 下一步（M2）

1. `evaluate.py`：每手的目损、按段位折算胜率、等级。
2. `keypoints.py`：四类候选，合并成片段，再挑出 4+1 个。
3. 阶段 2 深度分析：关键点前后的局面跑 3000 visits，取长 PV。
4. `facts.py` 和模板讲解。
5. `site/` 查看器：棋盘用 SVG，横竖屏两种布局。
