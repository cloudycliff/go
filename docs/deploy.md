# 从零部署

这份文档写给想在自己电脑上搭一套的人：拉取自己（或孩子）在野狐的对局，用本机 KataGo 复盘，
生成静态网页，通过 GitHub 和 Cloudflare Pages 发布，每天自动更新。日常命令见 [README](../README.md)，
设计和取舍见 [design-v1.md](design-v1.md) 和 [progress.md](progress.md)。

整个流程不用大模型，也不需要任何 API Key：分析、讲解、统计都在本机完成。联网的只有两处：从野狐下载棋谱，
和 `git push`。

## 1. 需要什么

| 项目 | 说明 |
|---|---|
| Windows 10/11 | 定时任务脚本是 Windows 的（`scripts\update.cmd`、`scripts\schedule.ps1`）。命令本身是跨平台的 Python。 |
| NVIDIA 显卡 | KataGo 用 CUDA 版。开发机是 RTX 5060 Ti 8 GB：一盘 250 手的棋，整盘分析约 2 分钟，加上深度分析等约 5～7 分钟。显存 4 GB 以上应该够用；没有显卡可以换 KataGo 的 Eigen（CPU）版，但会慢很多倍。 |
| Python 3.11+ | 只用标准库，不用 `pip install`。 |
| Git | 以及一个 GitHub 账号。本机要能 `git push`（HTTPS 凭据或 SSH key 配好）。 |
| Cloudflare 账号 | 免费版就够，用 Pages 托管网站。 |
| 野狐账号昵称 | 要复盘的那个账号。只用野狐的公开接口，不需要登录。 |

## 2. 准备 KataGo 和模型

需要三样东西，路径都写在 `config.toml` 里（下一步）：

1. **KataGo 程序**（CUDA 版，v1.15 以上，要支持 `-human-model`）和**主权重**。
   - 最省事：下载 LizzieYzy Next 的 NVIDIA 便携版，里面有 `app\engines\katago\windows-x64\katago.exe` 和
     `app\weights\default.bin.gz`，开发机就是这样用的。
   - 也可以从 KataGo 官方 GitHub Releases 下载程序，从 katagotraining.org 下载任意一个权重。
2. **HumanSL 模型**：`b18c384nbt-humanv0.bin.gz`，放到本项目的 `models/` 目录：
   https://media.katagotraining.org/uploaded/networks/models_extra/b18c384nbt-humanv0.bin.gz
   （SHA-256 `637746e44f0efe00ad1245a50aa9bbf0716efe364c43965ead97bd6835d84ab5`）。它用来判断"同级别的人会怎么下"，
   是按段位判错和推荐的基础，必须有。
3. **分析配置**：仓库里的 `katago/analysis.cfg`，一般不用改。显卡较弱、跑得太慢或显存不够时，
   把 `numAnalysisThreads` 和 `nnMaxBatchSize` 调小（比如 4 和 32）。

`models/`、`logs/` 和 `config.toml` 都在 `.gitignore` 里，不会被提交。

## 3. 拿到代码并配置

1. 在 GitHub 上新建一个**空**仓库，把本项目的代码推上去（或者 fork 后克隆到本机）。
   - 原仓库里的 `raw/` 和 `site/data/` 是原作者的对局数据，换成自己的之前先删掉：
     删除 `raw/` 下全部文件、`site/data/` 下全部文件，再提交。
2. 复制配置文件：

   ```
   copy config.example.toml config.toml
   ```

   改三处：`fox_nickname` 填野狐昵称；`[katago]` 的 `exe` 和 `model` 填上一步的路径（相对路径以项目目录为准）。
3. 在项目目录里检查一下（**所有命令都要在项目目录里运行**，否则 Python 可能找到别的同名 `pipeline` 包）：

   ```
   python -m unittest discover -s tests
   python -m pipeline list
   ```

   第二条应列出最近的 19 路对局。报"找不到野狐昵称为……的账号"就检查昵称。
4. 设好提交用的身份（只对本仓库）：

   ```
   git config user.name "你的名字"
   git config user.email "你的邮箱"
   ```

## 4. 分析第一局，本地预览

```
python -m pipeline analyze 1      # list 里的第 1 局：整盘分析 → 深度分析 → 生成 site/data
python -m pipeline serve          # 打开 http://localhost:8000/
```

手机或 iPad 在同一个 Wi-Fi 下预览：`python -m pipeline serve --bind 0.0.0.0`，再用电脑的局域网 IP 访问。

想多准备几局再上线：`python -m pipeline collect` 只做整盘分析、存在本机 `local/raw/`（不发布）；
以后 `analyze <棋局 ID>` 会用上已有的分析，并把它变成可发布的复盘。

## 5. 发布到 Cloudflare Pages

1. 把数据推到 GitHub：

   ```
   python -m pipeline publish
   ```

   它只提交 `site/` 和 `raw/` 两个目录，并推送到 `origin main`（只在 `main` 分支上发布）。
2. 在 Cloudflare 控制台：Workers & Pages → 创建 → Pages → 连接到 Git，选这个仓库，然后：
   - 生产分支：`main`
   - 框架预设：无；**构建命令留空**
   - **构建输出目录：`site`**
3. 保存后第一次部署完成，会得到一个 `https://<项目名>.pages.dev/` 网址。以后每次推送，十几秒到一两分钟内自动更新。
4. 如果 Cloudflare 提示仓库"disconnected from your Git account"：到 GitHub 设置 → Applications 里的
   Cloudflare Workers and Pages，重新给这个仓库授权，再推一个提交（`git commit --allow-empty -m redeploy`）触发部署。

网站是纯静态的，没有登录，任何拿到网址的人都能看。站点带了 `noindex`（`site/_headers`、`site/robots.txt`），
搜索引擎不会收录。

## 6. 多盘统计页面（可选）

对局有十来局以后，生成"我的常见问题""做题练习""好棋集锦"三个页面的数据：

```
python -m pipeline stats          # 先在本机生成，serve 预览
python -m pipeline stats --site   # 确认没问题后放进 site/，再 publish
```

放进 `site/` 一次以后，之后每次生成新的复盘都会自动更新这三页的数据，不用再手动运行。
`local/report.md` 是给家长看的详细统计，只在本机。

## 7. 每天自动更新

```
powershell -ExecutionPolicy Bypass -File scripts\schedule.ps1
```

它注册一个叫 `go-review-update` 的 Windows 计划任务，每天凌晨 2:00 运行 `scripts\update.cmd`，
也就是 `python -m pipeline analyze --latest --publish --max 10`：

- 只处理比已分析的最新一局更晚的 19 路、40 手以上的对局，一次最多 10 局；没有新对局几秒钟就结束，不启动 KataGo、不提交。
- 在后台运行（不弹窗口），用当前用户的身份，**只在这个用户登录 Windows 时运行**（锁屏可以，注销或关机不行）。
  会把电脑从睡眠中唤醒；2:00 时关机的话，下次开机后补跑。3 小时没跑完会被停止。
- 日志在 `logs\update.log`，每次以 `==== 日期 时间` 开头、`==== exit code N` 结尾，0 表示正常。
- 改时间：`powershell -ExecutionPolicy Bypass -File scripts\schedule.ps1 -At 03:00`；
  删除：`Unregister-ScheduledTask -TaskName go-review-update`；手动跑一次：`Start-ScheduledTask -TaskName go-review-update`。

## 8. 隐私：哪些东西会公开

| 位置 | 内容 | 公开给谁 |
|---|---|---|
| 网站（`site/`） | 棋谱、分析、讲解、统计。**自己的昵称一律替换成"我"**；对手的昵称和段位会显示 | 拿到网址的人 |
| GitHub 仓库的 `raw/` | 每局的原始棋谱和 KataGo 原始结果，**原始棋谱里有双方的野狐昵称** | 仓库公开时任何人 |
| 只在本机 | `config.toml`（昵称）、`models/`、`logs/`、`local/`（未发布的分析和详细统计）、做题记录（在浏览器里） | 不公开 |

不想让昵称出现在 GitHub 上，可以把仓库设为**私有**（Cloudflare Pages 支持私有仓库，网站照常更新）；
仓库一旦公开过，git 历史里的内容就可能已被别人拿到，私有化要在第一次推送数据之前做。

## 9. 常见问题

- **`python -m pipeline` 报找不到命令或行为奇怪**：没在项目目录里运行。
- **KataGo 启动失败**：看 `logs\katago\` 里的日志；多半是路径不对、显卡驱动太旧（CUDA 版要较新的驱动），
  或显存不够（调小 `analysis.cfg` 里的线程数和 batch）。
- **野狐接口报错**：这是非官方接口，可能临时失败或改版。可以先在野狐客户端导出 SGF，用
  `python -m pipeline analyze --sgf 文件.sgf --color B`（自己执黑填 B，执白填 W）。
- **推送失败**：在项目目录里手动 `git push` 看报错，通常是凭据过期。计划任务以当前用户运行，用的是同一套凭据。
- **改了算法想重新生成全部页面**：`python -m pipeline build`（缺的深度分析会补算；加 `--no-engine` 则不启动 KataGo）。
