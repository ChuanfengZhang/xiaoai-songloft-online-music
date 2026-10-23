# 运维与排障

命令在项目根目录执行，容器名称默认 `xiaoai-songloft-online-music-songloft`、`xiaoai-songloft-online-music-uzz`。本指南只覆盖本项目的新安装。

## 状态、启停与日志

```sh
python3 scripts/deploy.py status
docker stop xiaoai-songloft-online-music-uzz
docker start xiaoai-songloft-online-music-uzz
docker restart xiaoai-songloft-online-music-uzz
docker logs --tail 80 xiaoai-songloft-online-music-uzz
```

UZZ 重启后需要重新预热。本地曲库和已落盘的在线歌曲不依赖 UZZ。Docker 的 `unless-stopped` 可以恢复退出的进程，但不会仅因为 healthcheck 为 unhealthy 就重启容器。

Songloft 重启会中断播放，选择合适时间执行：

```sh
docker restart xiaoai-songloft-online-music-songloft
```

分享 Songloft 日志前检查账号、对话、签名音频 URL 和令牌。不要分享 `config.json`、`.runtime/` 或完整 `docker inspect` 输出。

## 核对版本与目录

```sh
docker exec xiaoai-songloft-online-music-songloft /app/data/songloft -version
docker inspect --format '{{range .Mounts}}{{if or (eq .Destination "/app/music") (eq .Destination "/app/music/uzz-online")}}{{.Destination}} writable={{.RW}}{{println}}{{end}}{{end}}' xiaoai-songloft-online-music-songloft
docker exec xiaoai-songloft-online-music-songloft sh -c 'probe=$(mktemp /app/music/uzz-online/.write-check.XXXXXX) || exit 1; rm "$probe" && echo downloads=write-ok'
```

预期版本为 v2.13.5，`/app/music` 的 `writable=false`，`/app/music/uzz-online` 的 `writable=true`，并输出 `downloads=write-ok`。挂载标记用于确认父曲库只读；下载目录另通过创建并删除临时空文件确认实际写入能力。不要以 `test -w` 单独判断只读挂载。父目录的只读挂载不妨碍播放；音箱实际访问的是 Songloft 对外地址。

`config.json` 改动不会自动更新容器环境、端口或挂载；`docker restart` 也不会应用这些改动。首次创建由部署脚本负责；后续重建应先备份、停用并核对当前容器，不能反复运行 start 覆盖现场。脚本发现同名容器会停止。

## 首次启动中途失败

若提示缺少部署文件或文件校验不通过，先执行 `python3 scripts/deploy.py check`，按输出将原始插件 ZIP 放入 `plugins/`、服务 tar.gz 放入 `packages/`。文件名与内容均须匹配 `versions.json`；不要手工解包或改名代替版本匹配。物料检查失败时，`start` 尚未调用 Docker，也未创建数据目录，补齐后可直接重试。

部署脚本不自动删除部分创建的容器，以便保留错误现场。先运行 `docker ps -a` 和本项目的 status，核对名称、日志和文件系统。不要执行全局 prune。

若只是 UZZ 暂时访问不了网站，而 Songloft 已正常运行，可先配置本地播放，再处理源网络。若两个容器已经创建且只是停止状态，可以分别 `docker start xiaoai-songloft-online-music-songloft`、`docker start xiaoai-songloft-online-music-uzz`。

确需重新运行首次创建时，确认容器名称及需要保留的数据后，仅停止和移除对应容器。保留宿主数据目录、原曲库和 `uzz-online`，不要加卷删除或清理磁盘的命令。配置和现有数据库不匹配时停止处理，先查明原因。

数据目录中的 `.xiaoai-songloft-online-music.json` 保存本次 `deployment_id`。首次安装只接受空目录；带有相同归属标记的目录可供本次安装重试或重建使用。重建前必须确认没有其他容器使用该数据目录，并保留原 `config.json` 和归属标记。非空目录没有标记、标记损坏或属于其他部署时，脚本会拒绝接管。不要删除或伪造标记来绕过检查；已有实例的导入不属于本安装脚本的功能。

## 故障定位顺序

| 现象 | 优先检查 |
| --- | --- |
| 容器启动后退出或反复重启 | 数据目录可写且允许执行；日志中的 permission denied；内存/OOM 状态 |
| 容器间连接失败 | 检查目标容器的运行状态、专用网络和服务别名 |
| 音箱不播放本地歌曲 | MIoT 登录/设备管理、歌曲索引、音箱能否访问 主机局域网地址和端口 |
| 语音后 search 计数不增加 | MIoT 实际收到的语音文本、规则、本地命中和外部搜索开关 |
| search 增加但 resolve 为零 | 候选不匹配、歧义、来源未启用或“不入库直接播放”等设置 |
| 取链成功但未发声 | URL 是否仍有效、主机能否取流、音箱到 Songloft 的地址与网络 |
| 播放了但未转 local | 等待完整缓存；下载插件的自动下载、路径模板和目录写权限 |
| 上游网站连接失败 | 按下方“上游网络连接”检查主机到上游网页和音频 CDN 的网络连通性 |

上游超时、临时网络失败或 HTTP 5xx 会使当前在线请求失败；冷却 3 秒后允许新的点播请求，不在后台自动重试。认证失败、限流或响应异常会进入 `needs_attention`，需要人工检查正常上游访问；服务不自动处理交互验证。临时音频 URL 不作为长期库地址保存；落盘后依赖本地文件。

### 上游网络连接

UZZ 当前通过 [m.uzz.me](https://m.uzz.me/) 获取搜索结果和播放链接，具体来源关系见[第三方说明](../THIRD_PARTY.md)。在线兜底需要 Docker 主机能访问该网页及返回的音频 CDN。

遇到 `needs_attention` 或上游连接失败时，先在与 Docker 主机相同网络的设备中打开该网页，检查能否正常加载和搜索。同网络浏览器可访问仅是初步检查；仍需结合 UZZ 健康状态确认容器侧连接。网页可用而音频无法读取时，继续检查音频 CDN 的连通性；不要将签名音频 URL 或令牌粘贴到公开日志中。

## 备份与维护

保存本项目部署脚本、发布物料和版本记录；私下备份 `config.json`，不要把它混入对外分享目录。备份 Songloft 数据目录（包含隐藏的归属标记、数据库、插件设置和账号状态），同时保护原曲库与新增歌曲。

需要一致性数据库备份时停用写入或使用已验证的快照/数据库备份方案；不要把正在写入的数据库目录普通复制视为可靠备份。恢复配置和数据后先核对权限，再启动并复查本地播放。

升级时分别评估 Songloft、插件和 Browserless，不自动跟随 latest。更新官方来源、版本和哈希后，重新验证本地播放、在线新歌、自动本地化与恢复。插件若启用了自动更新，应记录实际版本，避免与 versions.json 偏离。
