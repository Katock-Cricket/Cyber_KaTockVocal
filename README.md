# Cyber_KaTockVocal

本机运行的 KTV 物料准备工具。输入歌名或 Apple Music 链接，工具自动完成下载、封面、歌词、两段人声分离，把开录所需的 7 个文件放进 `D:\Videos\<歌名>\`。

界面在浏览器里，服务只监听 `127.0.0.1:8765`，音频与账号数据都留在本机。

## 它做什么

一次任务包含 6 个阶段，前 5 个在界面上可见：

| 阶段 | 做什么 | 产物 |
|---|---|---|
| download | 通过 Wrapper 解密下载 Apple Music 音源 | `<曲名>.flac` |
| cover | 取最高分辨率封面，写入 FLAC 元数据 | `封面.jpg` |
| lyrics | 取 Apple 官方歌词，生成 LRC 与 SRT；外语歌逐句附中文译文 | `歌词.lrc`、`歌词.srt` |
| pass1 | `melband_roformer_inst_v2` 分离出器乐与完整人声 | `伴奏.wav` |
| pass2 | 卡拉 OK 模型把完整人声拆成领唱与和声 | `主音.wav`、`和声.wav` |
| finalize | 校验规格、写状态文件、清理中间件 | `.ktvmeta.json` |

关键约束：原曲保持下载得到的采样率与位深；三个分离轨固定 44100 Hz / 16 bit / 立体声；歌词逐句与 Apple 原文一致，繁简形态与括号和声行都保留。

## 产出物

```
D:\Videos\<歌名>\
├── <曲名>.flac       原曲，文件名为曲名
├── 伴奏.wav
├── 主音.wav
├── 和声.wav
├── 封面.jpg
├── 歌词.lrc
├── 歌词.srt
└── .ktvmeta.json     内部状态文件，支撑增量与重跑
```

单曲约 200~250 MB。目录名与文件名按固定规则净化，同一首歌二次执行会命中同一目录。

## 环境要求

软件依赖若干本机已配置的外部程序，它们需要一次性搭好。完整搭建步骤见 [`docs/get-started.md`](docs/get-started.md)，下面是要点：

| 依赖 | 用途 | 本机默认位置 | 必需 |
|---|---|---|---|
| Windows 10/11 | 运行平台，依赖 DPAPI 与桌面通知 | — | 是 |
| Docker Desktop | 运行 Wrapper 容器 | `C:\Users\<用户>\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe` | 是 |
| Wrapper（classic 双端口版） | Apple Music 解密服务，占用 10020 / 20020 | `D:\Download\Wrapper.x86_64.latest` | 是 |
| GPAC / MP4Box | 下载器解封装 | `D:\GPAC` | 是 |
| ffmpeg / ffprobe | 转码、校验、写元数据 | `D:\ffmpeg\bin` | 是 |
| UVR 与两个模型 | 仅提供模型文件，分离由 audio-separator 执行 | `D:\Ultimate Vocal Remover` | 是 |
| Python 3.12 + uv | 网页进程与工作进程 | 项目 `.venv` | 是 |
| Node 22 + pnpm | 前端构建 | `frontend/` | 是（首次构建） |
| Go 1.23+ | 编译下载器到 `tools\amd\amd.exe` | 仅编译期 | 是（首次编译） |
| Apple Music 订阅 | 音源与歌词来源 | 用户自备 | 是 |
| OpenAI 兼容接口 | 外语歌词翻译，可选功能 | 任意兼容服务 | 否 |

各外部依赖的默认路径写在 `var/config.toml`，与本机不同时在设置页或该文件里改。

## 安装

在已经装好上表依赖的机器上，三步即可：

```powershell
# 1. 建 venv、装依赖、编译下载器、装分离工具
scripts\setup.ps1

# 2. 构建前端（setup.ps1 只装依赖，不打包）
pnpm -C frontend build

# 3. 日常启动
KaTockVocal.cmd
```

`KaTockVocal.cmd` 启动网页进程并打开浏览器，应用会自动拉起 Docker Desktop、启动 Wrapper 容器、跑 9 项体检。冷机首次启动时，Docker 等待 30~60 秒属正常。

## 首次配置

体检通过后还需要三件账号相关的事，缺哪件都只影响对应阶段：

1. **Apple ID 登录**：点体检条里的登录项，输入账号密码；出现 2FA 提示时在 60 秒内填入 6 位验证码。登录态缓存在容器里，后续启动直接复用。
2. **media-user-token**：歌词与部分音源需要它。在 Apple Music 网页版登录后打开开发者工具，从 `music.apple.com` 的 Cookie 中复制 `media-user-token` 的值，填到设置页。
3. **翻译接口（可选）**：设置页填 base_url、模型名、密钥，点「测试连接」。也可以启动前设置环境变量 `OPENAI_API_KEY`，应用首次启动时会导入并加密存储。「测试连接」按「地址可达 → 密钥有效 → 模型存在」三步依次验证，失败时指名具体哪一步。

密钥只以 Windows DPAPI 密文存进本地数据库，界面与日志中只显示「已设置/未设置」。

## 日常使用

搜歌环节支持关键词（中、英、日、德任意语言）与 Apple Music 单曲/专辑/歌单链接。候选列表显示封面、歌手、专辑、时长、年份，Live、Remix、Instrumental 这类版本会打标签；已经备过料的曲目带角标，点角标直接打开目录。

选中后进入队列，FIFO 执行。队列持久化，应用或电脑重启后未完成的曲目继续跑。顶部显示整体剩余时间，数值来自历史耗时样本的中位数，样本不足时给区间。

任务详情页可以单步重跑（下载、封面、歌词、pass1、pass2），也可以整首重来。已完成且产物存在的阶段会被跳过，覆盖前旧文件先进 `_backup_<时间戳>\` 子目录。

完成后点「打开文件夹」，把三条 WAV 拖进 DAW 即可开录。

## 代码结构

| 目录 | 内容 |
|---|---|
| `src/katock/web/` | 网页进程：HTTP 接口、体检、Docker 与 Wrapper、搜歌、工作进程守护 |
| `src/katock/worker/` | 工作进程：队列调度、阶段执行、写盘、通知 |
| `src/katock/adapters/` | 外部依赖适配器：docker、wrapper、catalog、downloader、ffmpeg、separator、translator |
| `src/katock/domain/` | 纯逻辑：命名、LRC/SRT、语言判定、ETA、产物映射 |
| `src/katock/storage/` | SQLite、`.ktvmeta.json`、原子写盘 |
| `src/katock/security/` | DPAPI 加密、日志脱敏 |
| `frontend/` | Vite + Vue 3 + Naive UI |
| `scripts/` | setup、setup-separator、build-downloader、dev |
| `var/` | 运行时数据：数据库、配置、工作目录、模型、日志（不入版本库） |
| `tools/` | 编译出的下载器与分离工具 venv（不入版本库） |

`var/config.toml` 存路径、并发、模型名等非敏感项；`var/katock.db` 存队列、耗时样本、歌词缓存与加密后的密钥；每个歌曲目录的 `.ktvmeta.json` 是该目录物料的权威状态。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/get-started.md`](docs/get-started.md) | 从零搭建运行时与开发环境，含下载链接、验证命令、排障 |
| [`docs/PRD.md`](docs/PRD.md) | 需求与验收标准 |
| [`docs/架构设计文档.md`](docs/架构设计文档.md) | 进程模型、适配器、流水线、数据表 |
| [`AGENTS.md`](AGENTS.md) | 协作规则与产品硬约束 |

## 常见问题

**界面打不开、`127.0.0.1:8765` 无响应**：先确认 `frontend/dist` 已构建，未构建时只有接口可用。再看 `var/logs/app.log`。

**体检里 Docker 一直显示「正在启动」**：首次冷启动需要 30~60 秒；超过 120 秒会判失败，检查 Docker Desktop 是否能独立启动，以及 `var/config.toml` 里的 `docker_desktop` 路径。

**Wrapper 容器起不来、日志里有 `unshare: Operation not permitted`**：`compose.yaml` 缺少 `privileged: true`。

**下载报「账号或令牌问题」**：先看体检的登录态；token 失效时重新登录，歌词单独失败则检查 media-user-token。

**分离很慢或报找不到模型**：确认 `var/models` 有 2 个 `.ckpt` 与 2 个 yaml，跑一次 `scripts\setup-separator.ps1` 可重建；显存不足时把分离并发降到 1。

**开始任务被拒绝，提示输出目录不可写或磁盘不足**：`D:\Videos` 需要可写，且必须与项目的 `var/work` 在同一块磁盘，否则原子落盘不可用；剩余空间低于 1 GB 会直接禁止新任务。

## 许可

MIT，见 [`LICENSE`](LICENSE)。Apple Music 账号、订阅与所下载内容的使用需自行遵守 Apple 的服务条款。
