# 第三方来源与许可

本仓库的部署脚本、配置模板及通用部署文档采用根目录的 Apache-2.0 许可证。UZZ 原创插件及取源服务配套物料由 Chuanfeng Zhang 保留版权，单独适用 [UZZ 配套物料使用说明](UZZ-LICENSE.md)，不包含在上述 Apache-2.0 授权范围中。以下第三方组件不因被引用、装入独立容器或随包提供而改变原许可和作者声明。

| 组件 | 来源 | 本仓库使用方式 |
| --- | --- | --- |
| Songloft v2.13.5 | [Docker Hub](https://hub.docker.com/r/songloft/songloft)、[仓库](https://github.com/songloft-org/songloft) | 使用官方 Full 镜像 `songloft/songloft:2.13.5`；镜像引用记录于 versions.json；不在 Git 中分发镜像层 |
| MIoT 2026.10.20.2 | [发布](https://github.com/songloft-org/songloft-plugin-miot/releases/tag/v2026.10.20.2) | 原始插件 ZIP 随包提供；包内声明 Apache-2.0，作者字段和内容不修改 |
| 歌曲下载 2026.10.8 | [发布](https://github.com/songloft-org/songloft-plugin-downloader/releases/tag/v2026.10.8) | 原始插件 ZIP 随包提供；包内声明 Apache-2.0，作者字段和内容不修改 |
| Browserless Chromium | [官方项目](https://github.com/browserless/browserless)、[许可](https://github.com/browserless/browserless/blob/main/LICENSE) | 只引用固定 amd64 镜像摘要，不重新分发镜像层；使用遵循相应上游许可 |
| m.uzz.me | [网站](https://m.uzz.me/) | 通过正常网页及其公开加载的前端请求搜索/取链；不是本项目维护的服务 |

MIoT 和下载插件的 Apache-2.0 许可文本见根目录 LICENSE；原始安装包校验值、版本和声明权限保留于 versions.json。UZZ 插件和取源服务的版本及校验值见 versions.json；两个包均携带 LICENSE.txt、THIRD_PARTY.md 和 APACHE-2.0.txt，分别说明 UZZ 使用范围及第三方归属。APACHE-2.0.txt 不表示 UZZ 原创物料采用 Apache-2.0。

本项目只做接口适配，不复制网站验证凭据、不关闭 TLS 校验、不处理交互验证。上述链接说明来源，不代表上游对本项目的背书或长期服务承诺。
