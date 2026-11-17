# go-review

把在野狐的对局拉下来，用本机 KataGo 复盘，生成静态网页发布到 Cloudflare Pages。

设计文档：[docs/design-v1.md](docs/design-v1.md)；进度：[docs/progress.md](docs/progress.md)

## 准备

1. Python 3.11+（只用标准库，无需安装依赖）。
2. KataGo 与主权重：默认使用 LizzieYzy Next 发行版里的 `katago.exe` 和 `default.bin.gz`，路径见 `config.example.toml`。
3. HumanSL 模型：从 KataGo 官方下载 `b18c384nbt-humanv0.bin.gz` 放到 `models/`
   （https://media.katagotraining.org/uploaded/networks/models_extra/b18c384nbt-humanv0.bin.gz ，
   SHA-256 `637746e44f0efe00ad1245a50aa9bbf0716efe364c43965ead97bd6835d84ab5`）。模型文件不入库。
4. `copy config.example.toml config.toml`，填入野狐昵称。`config.toml` 不入库。

命令都要在本目录里运行（本机 site-packages 里有个同名的 `pipeline` 包）。

## 使用

```
python -m pipeline list              # 最近的 19 路对局
python -m pipeline analyze --latest --publish   # 抓新对局 → 分析 → 提交推送（网站自动更新）；没有新对局就直接结束
python -m pipeline analyze 3         # 按序号或棋局 ID：整盘分析 → 深度分析 → 生成 site/data（加 --publish 顺便发布）
python -m pipeline analyze --sgf a.sgf --color B
python -m pipeline collect           # 在本机分析最近 20 局（只做整盘分析，存 local/raw/，不发布），给多盘统计用
python -m pipeline stats             # 多盘统计 → local/report.md 和“我的常见问题”页的数据（只在本机，serve 可预览；--site 才放进 site/）
python -m pipeline build             # 改了算法后，从 raw/ 重新生成全部页面数据（缺的深度分析和变化形势会补算；--no-engine 不跑 KataGo）
python -m pipeline serve             # 本地预览 http://localhost:8000/ （iPad 预览加 --bind 0.0.0.0）
python -m pipeline validate          # 用 10000 visits 和更强的人类档位复核关键点
python -m pipeline show <棋局ID>
python -m pipeline publish           # 只提交推送 site/ 和 raw/
python -m unittest discover -s tests
```

定时运行：`scripts\update.cmd` 等同于 `analyze --latest --publish`，输出追加到 `logs\update.log`，
可以直接挂到 Windows 任务计划程序。
