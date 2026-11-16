# go-review

把孩子在野狐的对局拉下来，用本机 KataGo 复盘，生成静态网页发布到 Cloudflare Pages。

设计文档：[docs/design-v1.md](docs/design-v1.md)；进度：[docs/progress.md](docs/progress.md)

## 准备

1. Python 3.11+（只用标准库，无需安装依赖）。
2. KataGo 与主权重：默认使用 LizzieYzy Next 发行版里的 `katago.exe` 和 `default.bin.gz`，路径见 `config.example.toml`。
3. HumanSL 模型：从 KataGo 官方下载 `b18c384nbt-humanv0.bin.gz` 放到 `models/`
   （https://media.katagotraining.org/uploaded/networks/models_extra/b18c384nbt-humanv0.bin.gz ，
   SHA-256 `637746e44f0efe00ad1245a50aa9bbf0716efe364c43965ead97bd6835d84ab5`）。模型文件不入库。
4. `copy config.example.toml config.toml`，填入野狐昵称。`config.toml` 不入库。

## 使用

```
python -m pipeline list              # 最近的 19 路对局
python -m pipeline analyze 3         # 按序号或棋局 ID 分析，结果写入 raw/
python -m pipeline analyze --sgf a.sgf --color B
python -m pipeline show <棋局ID>
python -m unittest discover -s tests
```
