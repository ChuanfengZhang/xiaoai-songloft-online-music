# xiaoai-songloft-online-music

小爱音箱 + Songloft：本地音乐优先，在线歌曲兜底。

让小爱音箱优先播放本地曲库；本地未命中时，通过 UZZ 插件搜索并播放在线歌曲，完整缓存后保存为本地歌曲，以后可离线点播。

公开目录包含部署工具和说明，运行所需的插件及取源服务包须单独补齐；完整交付包已放好这些物料。两者使用同一套安装命令，文件位置见[快速开始](#快速开始)。

**部署前请注意：本方案需要额外运行常驻的 Chromium 浏览器取源服务，默认共两个 Docker 容器。资源占用、启动等待和维护成本高于直接调用 HTTP API 的方案；请先阅读下方[浏览器依赖与运行成本](#浏览器依赖与运行成本)，再决定是否部署。**

## 让 AI 协助部署

将本仓库地址或完整目录交给 AI，并复制以下提示词：

```text
请阅读此项目的 README.md、versions.json 和 scripts/deploy.py，帮助我使用 Docker 部署小爱音箱的本地音乐与在线歌曲方案。
部署前先向我说明：在线兜底依赖额外常驻的 Chromium 取源容器，会增加内存占用、启动预热和维护成本；需要持续访问上游网页和音频 CDN。
先确认我的操作系统、CPU 架构、Docker 运行方式、音乐目录和网络条件。
结合主机剩余资源、已有服务和我的使用需求，评估是否适合长期运行这套方案；不要仅因 Docker 可运行就判断满足条件。
根据实际环境评估镜像与脚本是否适用；需要调整时说明适配方案，不要直接套用文档中的示例路径或默认架构。
按确认后的方案操作，保留已有服务和歌曲。
不要输出管理员密码、UZZ 令牌或完整私有配置。
小米账号登录和音箱播放检查由我完成；遇到错误时，请根据状态、日志与挂载配置定位。
```

自行安装请从[快速开始](#快速开始)阅读。

## 工作方式

本项目提供 Songloft 与 UZZ 的新安装方案和脚本，使用固定版本的 UZZ 插件与取源服务包。Songloft 负责曲库、音箱连接、播放缓存及本地化；UZZ 服务只负责在线搜索和播放前取链。

```text
语音点歌 → Songloft / MIoT → 本地曲库命中 → 播放本地文件
                            ↓ 未命中
                         UZZ 搜索 → 在线播放 → 完整缓存 → 写入 uzz-online
```

### 浏览器依赖与运行成本

当前 UZZ 实现通过浏览器页面及其会话完成在线搜索和播放前取链，必须同时运行独立的取源服务；仅上传 Songloft 插件不能使用在线兜底，普通反向代理也不能替代该浏览器会话。

- **资源占用**：除 Songloft 外，还需运行包含 Browserless、Chromium 和取源程序的容器。浏览器会保持会话，空闲时仍占用内存；镜像下载和磁盘占用也需要计入部署成本。
- **内存配置**：默认两个容器各设 1 GiB 内存上限，合计上限 2 GiB，不表示始终占用 2 GiB，也不表示主机仅有 2 GiB 内存就足够。请为系统、已有服务及运行峰值预留余量。
- **启动等待**：取源服务启动或恢复浏览器会话时需要预热。应等待 UZZ 返回 `ready` 后再使用在线兜底。
- **维护要求**：在线能力依赖浏览器、上游页面及音频 CDN；网页变化、访问限制或网络故障都可能使在线兜底暂不可用，需要按[运维说明](docs/operations.md)排查。

这套方案适合能够提供相应资源、并愿意维护额外 Docker 服务的环境。原有本地歌曲和已完整保存并转为本地的歌曲，不依赖 UZZ 取源服务运行。

## 部署条件与已验证环境

服务使用 Docker 容器运行，可部署在服务器、个人电脑或 NAS 上。需要可供容器访问的音乐目录、音箱能够访问的主机局域网地址，以及访问 Docker Hub、GHCR、上游音源服务和音频 CDN 的网络条件。上游来源见[第三方说明](THIRD_PARTY.md)，连接问题见[网络排障](docs/operations.md#上游网络连接)。

使用本仓库安装脚本还需要 Python 3.8+ 和 Docker 操作权限；只运行容器不需要在主机安装 Node 或 Puppeteer。脚本为全新安装设计，默认创建两个容器，每个容器内存上限为 1 GiB，应根据主机资源预留系统余量。

**参考验证环境：Linux amd64 群晖 NAS、小爱音箱 Pro（LX06），Docker Engine 24.0.2。**

当前脚本按 Linux 本机文件路径、Unix 权限及本地 Docker socket 编写，默认镜像固定为 `linux/amd64`。ARM、Windows、macOS、Docker Desktop 或远程 Docker 等环境尚未验证，可能需要调整镜像、路径、权限或网络配置；安装脚本当前会拒绝不匹配的执行环境，不应直接照搬。详见[兼容性与安装检查](docs/validation.md)。

### 固定版本

| 组件 | 版本 / 获取方式 |
| --- | --- |
| Songloft Full | **v2.13.5**，使用 [Docker Hub 官方镜像](https://hub.docker.com/r/songloft/songloft) `songloft/songloft:2.13.5` |
| Browserless Chromium | 固定 linux/amd64 镜像摘要，见 [versions.json](versions.json) |
| MIoT 插件 | 2026.10.20.2，配套文件位置见下文 |
| UZZ 插件 | 0.1.5，配套文件位置见下文 |
| 歌曲下载插件 | 2026.10.8，配套文件位置见下文 |

本项目使用 Songloft 包含 Web 界面的 Full 镜像，不使用 Lite 或 latest。启动时会检查程序自报版本，并按取得的镜像 ID 创建容器。

## 快速开始

### 1. 放置项目

将本仓库完整目录放在 Docker 主机上的持久存储位置，通过终端进入项目目录。目录位置由实际系统决定；后续命令都在项目根目录执行。

完整部署包已放好配套物料；如果取得的目录没有这些文件，请取得与 [versions.json](versions.json) 对应版本的物料，按以下结构放置。两种方式使用同一套脚本和后续步骤。

```text
项目根目录/
├── plugins/
│   ├── miot-2026.10.20.2.jsplugin.zip
│   ├── uzz-source-0.1.5.jsplugin.zip
│   └── downloader-2026.10.8.jsplugin.zip
└── packages/
    └── uzz-source-0.1.5.tar.gz
```

保持上述 ZIP 和 tar.gz 原文件，不要手工解包或只修改文件名来匹配版本。开始安装前执行：

```sh
python3 scripts/deploy.py check
```

该命令不读取私有配置、不调用 Docker；会检查四个文件是否齐全、校验值是否匹配。缺少文件时一次列出缺失清单、项目目录和放置要求，补齐后重新执行即可。后面的 `start` 也会自动检查，在物料检查通过前不会调用 Docker 或创建数据目录。

Songloft 数据目录必须持久可写，所在文件系统允许执行程序；启动时程序会复制到该目录再运行。避免使用带 `noexec` 的临时目录，例如部分 Linux 系统的 `/tmp`。

### 2. 生成配置

```sh
python3 scripts/deploy.py init
```

脚本生成权限为 `0600` 的 `config.json`，包含随机管理员密码、UZZ 令牌和部署标识，不打印凭据。已有配置不会覆盖。编辑其中这些字段：

| 字段 | 填写内容 |
| --- | --- |
| `host_ip` | 音箱可访问的 Docker 主机局域网 IPv4，例如 `192.168.1.100` |
| `music_dir` | **已经存在**的曲库绝对路径，Linux 路径示例为 `/srv/music`，请替换为实际目录 |
| `data_dir` | 本次安装专用的 Songloft 数据目录，首次安装须不存在或为空；Linux 路径示例为 `/srv/xiaoai-songloft-online-music/data`，请替换为实际目录；必须在曲库之外，所在文件系统允许执行程序 |
| `songloft_port` | 空闲的局域网端口，默认 `58091` |
| `admin_username` | Songloft 管理员用户名，默认 `admin` |

保留自动生成的 `admin_password`、`uzz_token`、`deployment_id`。不要将 `config.json` 发给别人或提交 Git；需要 AI 帮助时只提供脱敏配置和错误。

不要填写其他 Songloft 实例的数据目录。脚本只接管空目录，并写入本次部署的归属标记；以后重试创建时必须保留原 `config.json` 和数据目录中的标记，已有同名容器仍不会被覆盖。详见[首次启动中途失败](docs/operations.md#首次启动中途失败)。

### 3. 拉取镜像

```sh
python3 scripts/deploy.py pull
```

脚本从 Docker Hub 拉取 `songloft/songloft:2.13.5`，从 GHCR 拉取固定摘要的 Browserless 镜像，默认平台均为 `linux/amd64`。其他架构需要先选择匹配的镜像并调整版本配置和脚本。此步骤只下载镜像，不创建容器。

### 4. 创建并启动两个容器

```sh
python3 scripts/deploy.py start
```

脚本将：

1. 检查当前执行环境与脚本默认平台是否匹配，以及容器名称和配置。
2. 检查所需镜像；本地缺失时拉取，核对 Songloft 程序自报 `v2.13.5`，取源镜像保持固定摘要。
3. 创建 `data_dir` 和曲库中的 `uzz-online`，不移动原歌曲、不递归修改曲库权限。
4. 校验并解包固定版本 UZZ 服务包到 `.runtime/`，创建专用网络 `xiaoai-songloft-online-music`，启动 `xiaoai-songloft-online-music-songloft` 和 `xiaoai-songloft-online-music-uzz`。

Songloft 的原曲库挂载为只读，只有 `uzz-online` 子目录可写。子目录先在宿主机创建，再建立嵌套挂载。UZZ 服务不发布宿主端口，内部地址固定为 `http://uzz-source:3100`；浏览器后端端口也不公开。

**脚本不会覆盖、停止或删除已有同名容器。** 启动失败会保留现场供检查，不自动清理数据库。目录或端口权限不足时先按实际错误处理，不要给整个曲库递归放开权限。

### 5. 检查运行状态

```sh
python3 scripts/deploy.py status
```

等待约 30–90 秒，两容器应为 running，UZZ 应返回 `state: ready`。浏览器访问 `http://主机局域网IP:58091`（改过端口则使用新端口），使用 `config.json` 的管理员凭据登录。

看到 Songloft 页面还不代表音箱已配置，继续完成下列设置。

## 配置插件与音箱

### 安装插件

在 Songloft 的 JS 插件管理页，依次上传：

- `plugins/miot-2026.10.20.2.jsplugin.zip`
- `plugins/uzz-source-0.1.5.jsplugin.zip`
- `plugins/downloader-2026.10.8.jsplugin.zip`

页面不易找到时，可直接访问以下路径（接在 Songloft 地址后）：

| 页面 | 路径 |
| --- | --- |
| MIoT | `/api/v1/jsplugin/miot/` |
| UZZ | `/api/v1/jsplugin/uzz-source/` |
| 歌曲下载 | `/api/v1/jsplugin/downloader/` |

### 先验证本地播放

在 MIoT 中登录自己的小米账号，添加并启用目标音箱管理、对话监听和语音口令。将服务器地址填为 `http://主机局域网IP:端口`，音箱必须能够访问它；不能填 `localhost` 或内部服务名。

确认曲库路径为 `/app/music`，完成扫描，等待 MIoT 歌曲索引 ready。先实际点播一首原有本地歌曲，确认音箱发声。

### 连接 UZZ

在 UZZ 插件页面填入：

- 服务地址：`http://uzz-source:3100`
- 令牌：`config.json` 的 `uzz_token`

保存，点击“检查服务”，确认 ready；再点击“注册为 MIoT 候选”，确认成功。注册候选与开启外部搜索是两个步骤。

### 开启完整缓存转本地

在“歌曲下载”插件中：

- 路径模板：`uzz-online/{artist}-{title}`
- 嵌入元数据：先关闭
- 自动下载：开启并保存

该开关是 Songloft 的**全局配置**，也可能作用于其他插件来源的远程歌曲。首次配置时不要批量下载整个库。

### 设置本地优先、线上兜底

MIoT 页面“设置 → 语音 → 搜索（外部搜索源）”：

- 快速选择“UZZ 本地优先兜底”。
- 搜索优先级选择“本地优先”，超时先设为 6 秒。
- 关闭“不入库直接播放”，不自动追加现有歌单。
- 开启外部搜索并保存全部设置。

## 检查播放与自动保存

1. 点播一首原有本地歌，音箱应发声。
2. 点播一首本地没有的歌，明确说出歌手和歌名；确认音箱实际发声。
3. 等待完整缓存，在配置的音乐目录下看到 `uzz-online` 中的文件，Songloft 中该记录转为 `local`。
4. 再次点播，比较 UZZ `counts.search`、`counts.resolve`，应不再增加。
5. 临时执行 `docker stop xiaoai-songloft-online-music-uzz`，再次点播已落盘歌曲和原有本地歌；两者都应播放。完成后执行 `docker start xiaoai-songloft-online-music-uzz` 并等待 ready。
6. 在方便中断播放时重启 Songloft，再用另一首新歌检查配置和自动本地化恢复。

请确认音箱实际发声，并检查歌曲文件已保存。UZZ 服务重启会清零计数，比较搜索与取链次数时应保持服务持续运行。

支持环境及安装检查项见[兼容性与安装检查](docs/validation.md)。

## 日常使用与排障

常用启停、备份、版本核对和故障定位见[运维说明](docs/operations.md)。UZZ 暂停只影响线上兜底，已转本地的歌曲不依赖它。

常见情况：

- **容器重启、服务名解析失败**：先检查容器运行状态与 data 目录是否允许执行，不先修改全局 DNS。
- **搜索到但未发声**：搜索、取链、音频读取、音箱播放是不同阶段，按运维说明依次检查。
- **`startupNavigationStatus: 503` 但 ready**：前者是初始导航的历史状态，结合当前健康状态和请求结果判断。
- **`needs_attention`**：先确认家庭网络能否正常打开上游页面，不反复重启或自动处理交互验证。
- **语音点播结果不准确**：在 MIoT 中核对识别文本，并尝试明确说出歌手和歌名。

## 项目结构

```text
README.md                 安装、配置和播放检查入口
config.example.json       无凭据的配置模板
versions.json             版本、镜像引用及发布产物校验值
SHA256SUMS                公开部署文件校验清单
plugins/                  补齐物料后存在，完整交付包已包含
packages/                 补齐物料后存在，完整交付包已包含
scripts/                  部署、发布产物导入及完整性检查
tests/                    部署和依赖校验测试
docs/                     运维与验证范围
LICENSE                   项目许可证
UZZ-LICENSE.md            UZZ 配套物料的独立使用说明
THIRD_PARTY.md            上游来源和许可说明
```

文件获取、放置和安装前检查见[安装文件准备](docs/distribution.md)。配套物料的版本和 SHA-256 位于 `versions.json`，不写入公开文件清单 `SHA256SUMS`。

## 许可证

部署脚本、配置模板及通用部署文档采用 [Apache-2.0](LICENSE)。UZZ 原创插件、取源服务包及解包后的代码由 **Chuanfeng Zhang** 保留版权，单独适用 [UZZ 配套物料使用说明](UZZ-LICENSE.md)，不属于前述 Apache-2.0 授权范围。免费或付费获得者均可个人、家庭使用及自用修改；未经同意不公开分发、转售或打包进其他收费产品。

Songloft、MIoT、歌曲下载插件和 Browserless 保留各自的许可与作者声明，详见 [THIRD_PARTY.md](THIRD_PARTY.md)。本项目是独立适配，不代表相关上游项目或音源服务。
