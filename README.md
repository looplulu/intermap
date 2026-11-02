# 小路（Intermap）

面向中国中老年智能手机用户的连续任务导航助手。用户通过文字或语音提出目标，
App 分析经授权共享的画面，逐步播报操作指引，由用户自行操作。

## 当前版本与入口

`main` 是维护入口，2026-11-02 从阶段备份 `snapshot/xiaolu-1.1.02` 建立。
既有 `snapshot/xiaolu-*` 分支和 `xiaolu-*` 标签全部保留；不覆盖或删除历史快照。
后续代码修改走工作分支，完成阶段后另建版本快照，再同步维护入口。

1.1.02 为 Android 内部侧载试用版，支持一般 App 与系统任务入口。
没有自动点击、无障碍训练入口或自动发布地图；不能把构建和自动测试当作真机验收。
详见 [App 说明](App/README.md) 与 [1.1 接入及验收说明](digital-interaction-engine/docs/14-consumer-pilot-1.1.md)。

## 目录与文档

| 目录 | 用途 |
| --- | --- |
| `App/` | Flutter App 与 Android 原生录屏、悬浮窗、语音功能 |
| `digital-interaction-engine/` | 导航服务、Python 研究引擎、测试和技术文档 |
| `digital-interaction-demo/` | 网页演示与历史训练工作台 |

- [产品定义](digital-interaction-engine/docs/00-project-context.md)
- [当前试用版协议、运维与已知限制](digital-interaction-engine/docs/14-consumer-pilot-1.1.md)
- [历史训练交接](digital-interaction-engine/docs/07-training-handoff.md)
- [完整阶段交接](HANDOFF.md)与 [AI 维护约定](AGENTS.md)

旧训练、无障碍和地图优先方案是历史资料，不能当作 1.1 APK 已开放的功能。

## 本地开发与安全边界

Flutter 安装、检查与 APK 构建命令见 `App/README.md`；后端环境和测试见 1.1 说明。
模型密钥仅保存在服务端。真实环境文件、训练密码、账号、数据库、用户录屏、
上传文件、本地环境、构建缓存与 APK 不提交到源码仓库。

网站子站仍使用 `https://loop-lulu.com/intermap/`，由私有 `looplulu/home` 仓库维护；
它与本仓库的 App、演示目录不同。服务器历史训练数据和新版反馈独立保存，
源码整理不得删除或覆盖它们。
