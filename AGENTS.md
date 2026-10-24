# AGENTS.md

Cyber_KaTockVocal 是一个本机运行的 KTV 物料准备工具：输入歌名或 Apple Music 链接，自动产出原曲、伴奏、主音、和声、封面、歌词，放进 `D:\Videos\<歌名>\`。

本文件是所有参与本仓库开发的人与 Agent 的协作规则。

---

## 1. 开工前必读

按顺序阅读：

1. [`docs/PRD.md`](docs/PRD.md)：做什么、验收标准是什么。
2. [`docs/架构设计文档.md`](docs/架构设计文档.md)：怎么做、代码放哪里、当前 TODO。
3. [`docs/get-started.md`](docs/get-started.md)：外部依赖怎么装、怎么验证、怎么排障。
4. 本文件：必须遵守的规则。

四者出现冲突时，以 PRD 为准，并同步修正其他文档。

---

## 2. 文档规则（适用于仓库内全部文档）

1. **只记录当前状态**：文档仅描述软件当前已确认的结论与 TODO。结论变化时，直接把原文改写为新结论。
2. **正向描述范围**：用“只 / 仅做什么”来写边界，例如“仅读写交付物文件名与 `.ktvmeta.json`”。
3. **待定事项集中管理**：尚未确认的内容一律写进所属文档的 TODO 小节，写清“事项”与“完成标准”；完成后从 TODO 移除，并把结论写入正文。
4. **面向人类阅读**：先给结论，再给细节；表格只放短条目；术语与 PRD 第三节保持一致。
5. 文档、界面文案、代码注释统一使用中文；代码标识符使用英文。

---

## 3. 运行环境

| 项 | 约定 |
|---|---|
| 操作系统 | Windows 10/11；终端使用 PowerShell 语法 |
| Python | 3.12，项目代码仅使用根目录的专属 venv `.venv`（uv 创建与锁定），仅服务本项目 |
| 前端 | Node 22 + pnpm，位于 `frontend/` |
| Go | 仅用于编译下载器到 `tools\amd\amd.exe` |
| 外部程序 | ffmpeg / ffprobe：`D:\ffmpeg\bin`；MP4Box：`D:\GPAC`；UVR 模型：`D:\Ultimate Vocal Remover`；Wrapper：`D:\Download\Wrapper.x86_64.latest` |
| 分离工具 | `audio-separator` CLI，安装在独立 venv `tools\audio-separator\.venv`（含 PyTorch cu128，本机仅依赖 NVIDIA 驱动）；模型来自 UVR 安装目录 |
| Wrapper 与下载器参考 | 本机 skill `C:\Users\Administrator\.workbuddy\skills\apple-music-downloader`（构建、登录、2FA、排障） |
| 运行时数据 | 仅写入 `var/`（数据库、配置、工作目录、日志） |

所有外部路径都通过 `var/config.toml` 配置，代码中仅保留默认值。

---

## 4. 产品硬约束

实现时必须始终满足以下规则，评审时逐条核对。

### 4.1 数据边界

- 输出根目录 `D:\Videos` 仅按计算出的歌曲目录路径直接访问。
- 歌曲目录内仅读写 7 个交付物文件、`.ktvmeta.json`、`_backup_<时间戳>\` 子目录。原曲文件名是曲名加 `.flac`，不改成 `原曲.flac`。
- 覆盖本工具创建的文件前，先把旧文件移入 `_backup_<时间戳>\`。
- 外部目录（接入时原本没有 `.ktvmeta.json`）仅补缺失的文件，原有文件保持原样。
- 所有写盘经过 `storage/fsops.py`：先写 `var/work/<jobId>/`，校验后原子移动。

### 4.2 音频与语义

- 分离轨仅输出 WAV 44100 Hz / 16 bit / 立体声；原曲 FLAC 保持下载得到的采样率与位深。
- 模型输出到业务文件的映射仅在 `domain/stems.py` 中定义，严格按 PRD 附录 A。
- 歌词逐句原样输出：句子数、文字、繁简形态、括号和声行与 Apple 原文一致。
- 双语歌词仅在原文与译文句数一致时输出；否则输出单语版并标记“双语失败”。

### 4.3 运行与安全

- 服务仅绑定 `127.0.0.1`。
- Apple ID、密码、`media-user-token`、翻译密钥仅以 DPAPI 密文存入数据库；日志与接口仅显示脱敏结果。
- Docker Desktop 由应用负责拉起；应用退出时 Docker 保持原有运行状态。
- 分离并发上限为 2，下载并发固定为 1。
- 分离仅通过 `audio-separator` CLI 完成，项目 `.venv` 只装轻量依赖。

---

## 5. 代码约定

### 5.1 后端

- 分层：`domain/` 只放纯逻辑；外部程序与网络调用只放 `adapters/`；数据库与写盘只放 `storage/`。
- 外部程序一律以参数列表启动，路径原样传入，确保中文与空格可用。
- 每个适配器提供体检方法，失败信息精确到路径、端口或命令。
- 失败原因使用枚举分类，并配一句中文可执行建议。
- 工具：`ruff format`、`ruff check`、`mypy`、`pytest`；新增 `domain/` 与 `storage/` 逻辑须附带单元测试。

### 5.2 前端

- Vue 3 `<script setup>` + TypeScript；组件统一使用 Naive UI。
- 主题变量集中在 `n-config-provider`，默认深色主题。
- 接口调用仅经过 `src/api/`；实时数据仅经过 `useEventStream`。
- 状态文案集中在 `src/constants/status.ts`。
- 工具：`vue-tsc`、ESLint。

### 5.3 提交前自检

1. 后端 `ruff check`、`mypy`、`pytest` 通过。
2. 前端 `vue-tsc`、ESLint 通过。
3. 改动涉及第 4 节任一条，在说明中写明如何满足。
4. 改动涉及架构或范围，同步更新 `docs/架构设计文档.md`。

---

## 6. 当前状态

- 已确认：PRD、架构设计文档、本协作规则。工程脚手架、前后端与测试已落地。
- 翻译接口已确认：`https://api.chatanywhere.tech/v1`，模型 `deepseek-v4.1-flash-1017`。密钥只从 `OPENAI_API_KEY` 导入。
- 自动测试覆盖领域逻辑、写盘、假下载器/假分离器的六段流水线，以及本机目录解析与翻译连接测试。
- 待人工确认事项见架构设计文档第 13 节。Bohemian Rhapsody 已用真实令牌跑完下载、封面、双语歌词和两段分离。
