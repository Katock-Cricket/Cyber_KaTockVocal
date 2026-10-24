# 环境搭建指南

本文件说明如何在一台新的 Windows 机器上把 Cyber_KaTockVocal 跑起来。内容分两条路线：

- **运行时路线**：只想用这个工具备料，按第 1 至第 3 节顺序做一遍，第 4 节说明界面与产出物。
- **开发路线**：要改代码，在运行时路线之上再补第 5 节。

两条路线的前置条件相同。每一步都给出通过判据，判据不满足时往下走没有意义。

---

## 1. 前置条件

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11，x64。软件使用 DPAPI、`pywin32`、`windows-toasts`，不支持其他系统 |
| 磁盘 | 至少 40 GB 空闲。模型约 2.4 GB，分离工具 venv 约 5 GB，Docker 镜像约 1.5 GB，单曲产物约 250 MB |
| 磁盘布局 | 项目目录与输出根目录必须在同一块磁盘。原子落盘依赖同盘移动，体检会拦 |
| 显卡 | NVIDIA 独显，驱动支持 CUDA 12.8。分离走 GPU，纯 CPU 可以跑但耗时成倍增加 |
| 网络 | 需要访问 GitHub、Docker Hub、Apple 服务，以及你选的翻译接口 |
| 账号 | 有效的 Apple Music 订阅。音源与歌词都用它 |

磁盘布局是硬约束。默认配置里项目在 `D:\Workspace\Cyber_KaTockVocal`、输出在 `D:\Videos`，都在 D 盘。把项目放 C 盘、输出放 D 盘会让体检的 `output_root` 项直接失败。

---

## 2. 依赖一览

| 依赖 | 版本 | 体积 | 用途 | 获取方式 |
|---|---|---|---|---|
| Git | 任意近期版本 | 60 MB | 取代码 | <https://git-scm.com/download/win> |
| Python | 3.12（`>=3.12,<3.13`） | 30 MB | 网页进程与工作进程 | 由 uv 安装，见 3.2 |
| uv | 0.5 以上 | 15 MB | 建 venv、装依赖 | <https://docs.astral.sh/uv/getting-started/installation/> |
| Node.js | 22 LTS | 90 MB | 前端构建 | <https://nodejs.org/en/download> |
| pnpm | 9 以上 | 5 MB | 前端包管理 | <https://pnpm.io/installation>，或用 `corepack enable pnpm` |
| Go | 1.23.1 以上 | 200 MB | 编译下载器 | <https://go.dev/dl/> |
| Docker Desktop | 官方当前版本，支持 WSL 2 | 1.5 GB | 运行 Wrapper 容器 | <https://www.docker.com/products/docker-desktop/> |
| Wrapper（classic） | 发布标签 `wrapper.x86_64.latest` | 30 MB | Apple Music 解密 | <https://github.com/WorldObservationLog/wrapper/releases/tag/wrapper.x86_64.latest> |
| GPAC（MP4Box） | nightly | 100 MB | 下载器解封装 | <https://gpac.io/downloads/gpac-nightly-builds/> |
| ffmpeg / ffprobe | 6.0 以上 | 120 MB | 转码、校验、写元数据 | <https://www.gyan.dev/ffmpeg/builds/> 或 <https://github.com/BtbN/FFmpeg-Builds/releases> |
| Ultimate Vocal Remover | 当前稳定版 | 2 GB | 仅作为模型来源 | <https://ultimatevocalremover.com/> |
| UVR 模型（2 个 ckpt + 2 个 yaml） | 随 UVR | 2.4 GB | 两段分离 | UVR 内 Download Center，或 <https://github.com/TRvlvr/model_repo/releases> |
| apple-music-downloader | classic 版源码 | 5 MB | 编译 `tools\amd\amd.exe` | <https://github.com/zhaarey/apple-music-downloader>，见 3.4 |

分离本身由 `audio-separator` 执行，UVR 只提供模型文件。`audio-separator` 与它自带的 PyTorch 由 `scripts\setup-separator.ps1` 装进 `tools\audio-separator\.venv`，不用单独下载。

---

## 3. 运行时环境

目标：双击 `KaTockVocal.cmd` 能打开界面，9 项体检全绿，跑完一首歌得到 7 个文件。

### 3.1 取代码

```powershell
git clone <本仓库地址> D:\Workspace\Cyber_KaTockVocal
cd D:\Workspace\Cyber_KaTockVocal
```

通过判据：`AGENTS.md`、`pyproject.toml`、`scripts\setup.ps1` 三个文件都在。

`tools\` 与 `var\` 在 `.gitignore` 里，克隆下来不存在，后文会逐项生成。

### 3.2 Python 3.12 与 uv

```powershell
winget install --id=astral-sh.uv -e
uv --version
```

通过判据：`uv --version` 输出 0.5 以上版本号。

`pyproject.toml` 限定 `>=3.12,<3.13`。3.13 会因为 `pywin32` 与部分依赖装不上或行为不一致，装错版本时 `uv sync` 会直接报错，按提示重新执行 `uv venv --python 3.12 .venv` 即可。

uv 会自己下载 CPython 3.12，不需要预先装 Python。

### 3.3 Node 22 与 pnpm

```powershell
winget install --id=OpenJS.NodeJS.LTS -e
corepack enable pnpm
node --version
pnpm --version
```

通过判据：`node --version` 显示 `v22.x`，`pnpm --version` 显示 9 以上。

前端只需在首次安装和每次改动前端代码后构建一次，日常使用不再需要 Node。

### 3.4 下载器 `amd.exe`

下载器是 Go 程序，编译成 `tools\amd\amd.exe` 后由工作进程直接调用，运行时不需要 Go。

上游仓库的前沿版本已经改用单端口 `wrapper-lite`（`lite-server: http://127.0.0.1:12340`），本项目对接的是 classic 双端口版本，配置项为 `decrypt-m3u8-port` / `get-m3u8-port`，命令行支持 `--song`。已在 `a9ec9d6c3e23`（2026-07-08）验证可用；取更新的提交时按下面两条判据确认。

```powershell
git clone https://github.com/zhaarey/apple-music-downloader.git D:\Download\apple-music-downloader-main
cd D:\Download\apple-music-downloader-main
git checkout a9ec9d6c3e23
```

通过判据，两条都满足才算对：

```powershell
Select-String -Path config.yaml.example -Pattern "decrypt-m3u8-port"
Select-String -Path main.go -Pattern 'pflag.BoolVar\(&dl_song, "song"'
```

`main.go` 里搜不到 `--song`，或 `config.yaml.example` 里只有 `lite-server`，说明拿到的是 lite 版，本项目不能用。换 `git checkout` 的提交，或从已有环境直接拷一份 `tools\amd\amd.exe` 过来。

编译由 `scripts\setup.ps1` 调用 `scripts\build-downloader.ps1` 完成。脚本把 `GOPROXY` 设为 `https://goproxy.cn,direct`，国内网络可用；需要走其他代理时，编译前自行覆盖该环境变量。

源码里的 `config.yaml` 不需要手改。每次任务开工前，工作进程会在 `var\work\<jobId>\` 生成专用配置并清理。

### 3.5 Docker Desktop

```powershell
winget install --id=Docker.DockerDesktop -e
```

安装后启动一次，等托盘图标稳定，确认守护进程可用：

```powershell
docker info --format "{{.ServerVersion}}"
```

通过判据：输出一个版本号。

Docker Desktop 的默认安装路径是 `C:\Users\<用户名>\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe`。路径不同时改 `var/config.toml` 的 `docker_desktop`，或在设置页改。

应用会自己拉起 Docker Desktop，无需手动保持它开机自启。应用退出时 Docker 保持原来的运行状态。

拉取镜像超时的话，在 `%USERPROFILE%\.docker\daemon.json` 里加镜像加速并重启 Docker Desktop：

```json
{
  "registry-mirrors": ["https://docker.1ms.run", "https://docker.xuanyuan.me"]
}
```

### 3.6 Wrapper 解密服务

Wrapper 以 Docker 容器运行，向本机暴露 10020（解密）、20020（m3u8）、30020（账号信息）三个端口。下载器使用前两个端口取音源。

**取包**

下载 <https://github.com/WorldObservationLog/wrapper/releases/tag/wrapper.x86_64.latest> 里的 `Wrapper.x86_64.latest.zip`，解压到 `D:\Download\Wrapper.x86_64.latest`。

通过判据：目录里有 `compose.yaml`、`Dockerfile`、`entrypoint.sh`、`wrapper` 二进制、`rootfs\` 五个条目。

必须用这个发布包。仓库 `lite` 分支是单端口 12340 的新实现，与本项目的配置格式和端口约定都不一致。

**检查 compose.yaml**

三个端口映射和 `privileged` 缺一不可：

```yaml
services:
  app:
    privileged: true
    environment:
      USERNAME: ${USERNAME}
      PASSWORD: ${PASSWORD}
    ports:
      - "10020:10020"
      - "20020:20020"
      - "30020:30020"
    volumes:
      - ./rootfs/data:/app/rootfs/data
```

少了 `privileged: true`，容器会以 `unshare: Operation not permitted` 退出。

**构建镜像**

```powershell
cd D:\Download\Wrapper.x86_64.latest
docker compose build
```

通过判据：`docker images` 里出现这个目录对应的镜像。

构建基于 `debian:13.2`，网络不好时先 `docker pull debian:13.2` 再构建。镜像缺失时应用会自动触发一次构建，但那会把首次启动拖到十几分钟，建议提前做完。

**首次登录与 2FA**

账号密码可以用界面提交，也可以手动跑一遍。手动方式把整个流程走通一次，之后界面只管 `compose up -d`：

```powershell
cd D:\Download\Wrapper.x86_64.latest
$env:USERNAME="<Apple ID>"
$env:PASSWORD="<Apple ID 密码>"
docker compose up -d
docker logs --tail 30 <容器名>
```

日志出现 2FA 提示后，在 60 秒内把 6 位验证码写进容器。文件映射在 Windows 上有延迟，必须用 `docker exec` 在容器内部写：

```powershell
docker exec <容器名> sh -c "echo -n '<6位验证码>' > /app/rootfs/data/data/com.apple.android.music/files/2fa.txt"
```

通过判据：日志出现 `listening 0.0.0.0:10020`，且下面两条命令都能连上：

```powershell
Test-NetConnection 127.0.0.1 -Port 10020 -InformationLevel Quiet
Test-NetConnection 127.0.0.1 -Port 20020 -InformationLevel Quiet
```

登录成功后令牌库落在 `rootfs\data\...\mpl_db\kvs.sqlitedb`，后续启动只需 `docker compose up -d`。

验证码过期或登录失败时，清掉 `rootfs\data\data\com.apple.android.music\files\2fa.txt` 与同目录的 `mpl_db`，再重启容器重新走一遍。

### 3.7 GPAC（MP4Box）

从 <https://gpac.io/downloads/gpac-nightly-builds/> 下载 Windows 构建，解压到 `D:\GPAC`。

通过判据：

```powershell
D:\GPAC\mp4box.exe -version
```

体检按 `<gpac_dir>\mp4box.exe` 这个固定文件名检查。解压后如果多套了一层目录，把 `mp4box.exe` 提到 `D:\GPAC` 根下。

MP4Box 不需要加进系统 PATH。工作进程调用下载器时会把 GPAC 目录与 ffmpeg 目录拼进子进程的 `PATH`。

### 3.8 ffmpeg 与 ffprobe

下载 gyan.dev 的 `ffmpeg-release-essentials.zip`，解压后把 `bin` 目录里的 `ffmpeg.exe`、`ffprobe.exe` 放到 `D:\ffmpeg\bin`。

通过判据：

```powershell
D:\ffmpeg\bin\ffmpeg.exe -version
D:\ffmpeg\bin\ffprobe.exe -version
```

这两个程序负责 ALAC 转 FLAC、写元数据与内嵌封面、把分离结果统一成 16 bit PCM、以及所有规格校验。

### 3.9 UVR 与分离模型

UVR 只提供模型文件，界面上的分离按钮与自动流程无关，装完可以不开。

1. 从 <https://ultimatevocalremover.com/> 装 UVR 到 `D:\Ultimate Vocal Remover`。
2. 首次启动进入 Download Center，下载 `MelBand Roformer Kim | Inst V2 by Unwa` 与 `Karaoke MelBand Roformer` 两个模型。

通过判据，四个文件都在：

```powershell
$u = "D:\Ultimate Vocal Remover\models\MDX_Net_Models"
Test-Path "$u\melband_roformer_inst_v2.ckpt"
Test-Path "$u\mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
Test-Path "$u\model_data\mdx_c_configs\config_melbandroformer_inst_v2.yaml"
Test-Path "$u\model_data\mdx_c_configs\config_mel_band_roformer_karaoke.yaml"
```

UVR 安装位置不同时改 `var/config.toml` 的 `uvr_dir`，`scripts\setup-separator.ps1` 里也有同样的路径需要同步。

`setup-separator.ps1` 会把两个 ckpt 硬链接到 `var\models`，把两个 yaml 复制过去，其中卡拉 OK 的 yaml 按 audio-separator 的清单要求改名为 `mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956_config.yaml`。硬链接要求同盘：UVR 在 C 盘、项目在 D 盘时会失败，此时把脚本里的 `Link-File` 改成 `Copy-Item`。

不想装 UVR 时的替代路径：先按 3.10 装好分离工具，再让 audio-separator 把模型下到 `var\models`，然后逐项核对上面的四个文件名，缺 yaml 时按同名规则补上。

```powershell
tools\audio-separator\.venv\Scripts\audio-separator.exe --download_model_only `
  --model_filename melband_roformer_inst_v2.ckpt --model_file_dir var\models
```

### 3.10 一次性脚手架

```powershell
scripts\setup.ps1
```

这个脚本依次做四件事：`uv venv --python 3.12 .venv`、`uv sync`、`pnpm -C frontend install`、调用 `build-downloader.ps1` 与 `setup-separator.ps1`。

通过判据：

```powershell
.venv\Scripts\python.exe -c "import katock, fastapi; print('ok')"
Test-Path tools\amd\amd.exe
tools\audio-separator\.venv\Scripts\audio-separator.exe --version
```

分离工具的 venv 装的是 `audio-separator[gpu]` 加 PyTorch cu128。PyTorch 自带 CUDA 运行库，本机只需要 NVIDIA 驱动，不需要装 CUDA Toolkit。

没有 NVIDIA 显卡时，把 `setup-separator.ps1` 里的 `audio-separator[gpu]` 改成 `audio-separator[cpu]`，并删掉装 torch cu128 的那一行，再重新执行该脚本。CPU 模式下 ETA 默认系数（pass1 `0.24`、pass2 `0.28`）严重偏低，跑几首积累样本后会自行收敛。

### 3.11 构建前端

```powershell
pnpm -C frontend build
```

通过判据：`frontend\dist\index.html` 存在。

`setup.ps1` 只装依赖不打包，漏掉这一步时 `127.0.0.1:8765` 只有接口能访问，页面打不开。

### 3.12 首次启动与账号配置

```powershell
KaTockVocal.cmd
```

浏览器会自动打开 `http://127.0.0.1:8765`。首次运行会在 `var\` 下生成 `config.toml`、`katock.db`、`work\`、`models\`、`logs\`。

体检 9 项全绿之后，在设置页补齐三件事：

1. **Apple ID 与密码**：登录对话框提交后，应用用 `docker compose up -d` 把账号传给容器；需要验证码时界面弹出 6 位输入框，60 秒倒计时。密码只以 DPAPI 密文入库。
2. **media-user-token**：浏览器登录 Apple Music 网页版，开发者工具 → Application → Cookies → `https://music.apple.com`，复制 `media-user-token` 的值，粘到设置页。歌词与 AAC 音源依赖它。
3. **storefront**：与账号地区一致，中国区为 `cn`，美国区为 `us`。地区和账号不匹配会表现为「曲目不可获取」。

外语歌词要双语时，再加翻译接口：base_url、模型名、密钥，点「测试连接」。也可以先设环境变量再启动，应用首次启动时导入：

```powershell
$env:OPENAI_API_KEY = "<密钥>"
KaTockVocal.cmd
```

导入只在数据库里没有该密钥时发生一次，之后以设置页为准。

**收尾验证**：搜一首歌，选一条，等队列跑完，检查目录里 7 个文件齐全，`伴奏.wav` 与 `主音.wav` 听感对得上语义。

---

## 4. 界面与产出物

| 页面 | 用途 |
|---|---|
| 顶部体检条 | 9 项环境状态，点开看路径、端口、命令级定位与操作按钮 |
| 搜歌 | 关键词或链接，候选卡片带封面、版本标签、已备料角标 |
| 曲目清单 | 专辑/歌单解析结果，勾选后入队，默认勾未备料 |
| 队列 | 整体进度与剩余时间，单条卡片含分段进度与操作 |
| 任务详情 | 阶段时间线、预估与实际耗时、缺失清单、错误建议、复制日志、打开文件夹、单步重跑 |
| 设置 | 路径、并发、模型名、自动翻译开关、翻译接口与测试连接、Apple 账号、media-user-token、清理历史记录 |

歌曲目录只包含 7 个交付物与 `.ktvmeta.json`，覆盖前旧文件进 `_backup_<时间戳>\`。目录里原有的其他文件（录音、工程、素材）不会被改动。

---

## 5. 开发环境

运行时路线的全部内容都适用于开发，另外补四项。

### 5.1 前后端热重载

```powershell
scripts\dev.ps1
```

脚本用 `KATOCK_NO_BROWSER=1` 起 uvicorn（`--reload`，端口 8765），再起 Vite 开发服务器（5173），`/api` 由 Vite 代理到后端。开发时访问 5173。

`KATOCK_ROOT` 环境变量可以覆盖项目根目录，用于在同一台机器上跑第二份实例。

### 5.2 质量门禁

```powershell
.venv\Scripts\ruff format src tests
.venv\Scripts\ruff check src tests
.venv\Scripts\mypy
pnpm -C frontend typecheck
pnpm -C frontend lint
```

`mypy` 开 `disallow_untyped_defs`，新增函数需要写完整类型标注。

### 5.3 测试

```powershell
.venv\Scripts\pytest
```

三档测试，默认只跑不需要外部服务的部分：

| 标记 | 内容 | 触发方式 |
|---|---|---|
| 无标记 | 领域逻辑、写盘、假下载器与假分离器的流水线 | 直接跑 |
| `live` | 真实 Apple 目录接口、真实翻译接口、已启动的本机服务 | `pytest -m live`，服务未启动时自动跳过 |
| `slow` | 真实 GPU 分离 | `KATOCK_GPU=1` 后 `pytest -m slow` |

`live` 里的翻译检查读环境变量 `OPENAI_API_KEY`，未设置时跳过。

`tests\conftest.py` 把 ffmpeg 目录写死为 `D:\ffmpeg\bin`，换机器后要改这个常量，或把 ffmpeg 放到同一路径。

首次跑测试时会用 `go build` 生成 `tests\fakes\launcher.exe`，需要 Go 在 PATH 里。

### 5.4 代码边界

`domain/` 只放纯函数与数据结构；外部程序与网络调用只放 `adapters/`；数据库与写盘只放 `storage/`。新增适配器需要同时提供体检方法、调用方法与失败分类。改动的约束细则见 `AGENTS.md` 第 4 节。

---

## 6. 体检 9 项与通过判据

| 项 | 检查内容 | 通过判据 | 失败时 |
|---|---|---|---|
| docker | 守护进程可连接 | `docker info` 返回版本号 | 自动拉起 Desktop，轮询 120 秒，超时给「重新拉起」与日志入口 |
| wrapper | 容器运行中 | `docker compose ps` 有 running 记录 | 自动 `compose up -d`，镜像缺失时自动 build |
| wrapper_ports | 10020 与 20020 可连通 | 两个端口都能建连 | 显示具体端口与错误 |
| wrapper_login | 登录态有效 | 容器日志出现 `listening 0.0.0.0:10020` | 提示需重新登录，弹出登录对话框 |
| mp4box | `mp4box.exe -version` | 返回 GPAC 版本号 | 链接到设置页对应路径 |
| ffmpeg | `ffmpeg -version` | 返回版本号 | 同上 |
| separator | `audio-separator --version` 与 4 个模型文件 | 版本号可读，`var\models` 中 4 个文件齐备 | 列出缺失文件与期望路径 |
| output_root | 输出根目录可写，且与 `var\work` 同盘 | 写入探针文件成功，`Get-Volume` 同一盘符 | 阻止启动新任务 |
| disk | 剩余空间 | ≥ 5 GB | 低于 5 GB 警告，低于 1 GB 禁止新任务 |

体检每 30 秒重跑一次，也可以在界面上手动触发。

---

## 7. 配置项

`var\config.toml` 由应用首次启动时生成，设置页保存时整体重写。密钥不写在这个文件里。

| 键 | 默认值 | 说明 |
|---|---|---|
| `host` | `127.0.0.1` | 只接受回环地址，改成其他值会校验失败 |
| `port` | `8765` | 界面端口 |
| `output_root` | `D:\Videos` | 输出根目录，必须与项目 `var\work` 同盘 |
| `docker_desktop` | `C:\Users\Administrator\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe` | 换机器通常要改 |
| `wrapper_dir` | `D:\Download\Wrapper.x86_64.latest` | 需含 `compose.yaml` |
| `gpac_dir` | `D:\GPAC` | 需含 `mp4box.exe` |
| `ffmpeg_dir` | `D:\ffmpeg\bin` | 需含 `ffmpeg.exe`、`ffprobe.exe` |
| `uvr_dir` | `D:\Ultimate Vocal Remover` | 仅 `setup-separator.ps1` 读取 |
| `downloader_src` | `D:\Download\apple-music-downloader-main` | 仅 `build-downloader.ps1` 读取 |
| `storefront` | `cn` | 与 Apple 账号地区一致 |
| `separation_concurrency` | `2` | 只接受 1 或 2 |
| `translate_concurrency` | `1` | 只接受 1 到 3 |
| `pass1_model` | `melband_roformer_inst_v2.ckpt` | 第一段分离模型 |
| `pass2_model` | `mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt` | 第二段分离模型 |
| `pass1_yaml` | `config_melbandroformer_inst_v2.yaml` | 与 ckpt 同目录 |
| `pass2_yaml` | `mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956_config.yaml` | 改名后的 UVR 配置 |
| `translator_base_url` | `https://api.chatanywhere.tech/v1` | OpenAI 兼容接口地址 |
| `translator_model` | `deepseek-v4.1-flash-1017` | 翻译模型 |
| `auto_translate_lyrics` | `true` | 全局默认；单曲可在任务详情覆盖 |
| `eta_*` | 见文件 | ETA 冷启动系数，样本足够后自动以实测为准 |

敏感项（Apple ID、密码、media-user-token、翻译密钥）只存在 `var\katock.db` 的 `secrets` 表，密文由 DPAPI 保护。

DPAPI 密文绑定当前 Windows 用户与机器。换机器、换用户后必须重新填一遍这四项，直接拷贝 `katock.db` 无法解密。

---

## 8. 排障

| 现象 | 原因 | 处理 |
|---|---|---|
| `127.0.0.1:8765` 打不开页面 | 前端未构建 | `pnpm -C frontend build` |
| 启动即报端口占用 | 8765 被其他程序占用 | 改 `config.toml` 的 `port` |
| Docker 一直「正在启动」 | 冷启动慢，或守护进程起不来 | 等 60 秒；仍失败则单独开 Docker Desktop 看它自己的报错 |
| `docker compose build` 卡住 | 拉 `debian:13.2` 超时 | 配置镜像加速，或 `docker pull debian:13.2` 后重试 |
| Wrapper 退出，日志 `unshare: Operation not permitted` | 缺 `privileged: true` | 改 `compose.yaml` 后重建 |
| 2FA 写入后没反应 | Windows 文件映射延迟 | 用 `docker exec` 在容器内写 `2fa.txt` |
| 下载报「账号或令牌问题」 | 登录态失效或 media-user-token 缺失 | 重新登录，补 token；两者在界面分开显示 |
| 下载报「该曲目在当前地区不可获取」 | `storefront` 与账号地区不符，或该曲目下架 | 改 `storefront`，或换版本 |
| 分离报找不到模型 | `var\models` 缺文件 | 重跑 `setup-separator.ps1` |
| 分离 OOM 或极慢 | 显存不足 | 并发降到 1；仍不行换更小模型或 CPU 模式 |
| 体检 `output_root` 失败 | 目录不可写，或与 `var\work` 不同盘 | 把输出目录放到项目所在磁盘 |
| 双语歌词没有出现 | 中文语系不翻译；或翻译接口失败 | 看任务详情的「双语失败」标记与日志 |
| `uv sync` 报 Python 版本不符 | 用了 3.13 | `uv venv --python 3.12 .venv` 后重跑 |
| `go build` 超时 | 模块代理不可达 | 设 `GOPROXY=https://goproxy.cn,direct` |

日志位置：应用日志 `var\logs\app.log`（按天滚动，保留 14 天），任务日志 `var\logs\jobs\<jobId>.jsonl`（任务详情页的「复制完整日志」读的就是它）。

---

## 9. 迁移到另一台机器

按第 3 节重装外部依赖，另外需要带走的东西：

| 内容 | 是否可带走 | 说明 |
|---|---|---|
| 仓库代码 | 是 | 走 Git |
| `var\config.toml` | 是 | 路径变了要改 |
| `var\models\` | 是 | 2.4 GB，也可以在新机器重跑 `setup-separator.ps1` |
| `tools\amd\amd.exe` | 是 | 省一次 Go 编译 |
| `Wrapper\rootfs\data\` | 是 | 带登录令牌，可直接复用登录态 |
| `var\katock.db` | 有限 | 队列与历史可以带走，四个密钥因 DPAPI 绑定机器必须重填 |
| `tools\audio-separator\.venv` | 否 | 含绝对路径与已编译扩展，必须在新机器重装 |
| `frontend\dist` | 是 | 也可以在新机器重新构建 |

---

## 10. 自检顺序

按此顺序执行，每步判据不过就先停下修环境，不要继续往下调代码。

1. `git clone` 仓库，确认 `AGENTS.md`、`pyproject.toml`、`scripts\setup.ps1` 存在。
2. `uv --version`、`node --version`、`pnpm --version`、`go version` 有输出版本；启动 Docker Desktop 后 `docker info` 能返回版本号。
3. `scripts\setup.ps1` 无报错，`.venv\Scripts\python.exe -c "import katock"` 成功。
4. `Test-Path tools\amd\amd.exe` 为真；`tools\audio-separator\.venv\Scripts\audio-separator.exe --version` 能打印版本。
5. `var\models` 下 4 个模型文件齐备，两个 ckpt 各约 0.9 GB 与 1.5 GB。
6. `D:\GPAC\mp4box.exe -version`、`D:\ffmpeg\bin\ffmpeg.exe -version` 都能执行。
7. `docker compose ps` 在 Wrapper 目录显示容器 running，`Test-NetConnection 127.0.0.1 -Port 10020` 为真。
8. `pnpm -C frontend build` 生成 `frontend\dist\index.html`。
9. `.venv\Scripts\pytest` 通过，`.venv\Scripts\ruff check src tests` 与 `.venv\Scripts\mypy` 无报错。
10. 启动 `KaTockVocal.cmd`，`GET /api/health` 返回 9 项且 `canStartJobs` 为真。

不要做的事：不要删除 `var\` 或 `tools\` 目录，不要手改 `tools` 下的可执行文件，不要把密钥写进 `var\config.toml`，不要手动编辑 `Wrapper\rootfs\data\` 里的令牌文件（迁移时整目录复制即可）。
