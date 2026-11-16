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
5. AI 老师讲解（可选）：把 DeepSeek 的 API key 设为用户环境变量（不要写进任何文件）：
   `[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "<key>", "User")`。没有 key 时只用模板讲解。

命令都要在本目录里运行（本机 site-packages 里有个同名的 `pipeline` 包）。

## 使用

```
python -m pipeline list              # 最近的 19 路对局
python -m pipeline analyze 3         # 按序号或棋局 ID：整盘分析 → 深度分析 → 生成 site/data
python -m pipeline analyze --sgf a.sgf --color B
python -m pipeline build             # 改了算法后，从 raw/ 重新生成全部页面数据（--no-engine 不跑 KataGo，--no-llm 不请求 AI 讲解）
python -m pipeline serve             # 本地预览 http://localhost:8000/ （iPad 预览加 --bind 0.0.0.0）
python -m pipeline validate          # 用 10000 visits 和更强的人类档位复核关键点
python -m pipeline show <棋局ID>
python -m unittest discover -s tests
```
