# 安装文件准备

无论从仓库下载部署目录，还是取得完整安装包，都使用 [README](../README.md#快速开始) 中的同一套安装步骤。开始前，先确认所需文件是否齐全。

## 先检查是否需要补文件

解压后进入包含 `README.md` 和 `scripts/` 的项目目录，执行：

```sh
python3 scripts/deploy.py check
```

- **检查通过**：文件已齐全且版本匹配，继续 [生成配置](../README.md#2-生成配置)。完整安装包通常可直接通过这项检查。
- **提示缺少文件**：按输出中的文件名和路径补齐，再执行一次检查。已有的正确文件无需重复下载。
- **提示校验不通过**：文件可能下载不完整或版本不符，请重新取得对应版本的原始文件。不要修改校验值来跳过检查。

这项检查不会启动容器，也不需要填写管理员密码或服务令牌。

## 补齐缺少的文件

当前版本使用以下目录结构：

```text
项目目录/
├── README.md
├── scripts/
├── plugins/
│   ├── miot-2026.10.20.2.jsplugin.zip
│   ├── uzz-source-0.1.4.jsplugin.zip
│   └── downloader-2026.10.8.jsplugin.zip
└── packages/
    └── uzz-source-0.1.4.tar.gz
```

| 文件 | 获取及放置方式 |
| --- | --- |
| MIoT 插件 | 从[官方发布页](https://github.com/songloft-org/songloft-plugin-miot/releases/tag/v2026.10.20.2)获取该版本安装包，放入 `plugins/`，文件名按目录示例保存 |
| 歌曲下载插件 | 从[官方发布页](https://github.com/songloft-org/songloft-plugin-downloader/releases/tag/v2026.10.8)获取该版本安装包，放入 `plugins/`，文件名按目录示例保存 |
| UZZ 插件与取源服务 | 从 UZZ 配套包取得两个文件：插件 ZIP 放入 `plugins/`，服务 tar.gz 放入 `packages/`。两者缺一不可 |

目录不存在时可以自行创建。下载官方插件时选择实际的 `.jsplugin.zip` 安装包，不能使用 GitHub 的 `Source code` 源码压缩包。

四个文件均保持压缩包形式，不要手工解包；取源服务包会由安装脚本处理。不要用其他版本的文件改名替代所需版本。上述版本须与当前项目的 [versions.json](../versions.json) 一致，检查命令会核对文件内容。

## 文件齐全后继续安装

再次执行：

```sh
python3 scripts/deploy.py check
```

检查通过后，按照 [README 的生成配置步骤](../README.md#2-生成配置)继续。插件 ZIP 要保留到 Songloft 启动后，在插件管理页上传；仅将文件放入目录不会自动安装插件。

UZZ 配套物料的使用范围见 [UZZ 使用说明](../UZZ-LICENSE.md)，第三方组件的来源与许可见 [第三方说明](../THIRD_PARTY.md)。
