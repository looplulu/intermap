# Digital Interaction Engine（数字交互引擎）

> 数字世界的第一张高精交互地图（HD Interaction Map）。

## 一句话描述

以 AI 眼镜为载体，帮助中老年人重新获得数字世界的控制感。通过连续任务导航（Continuous Task Navigation），边导航边建图，让数字交互地图在真实使用中持续成长。

## 核心设计哲学

- **不要为了 AI 去设计地图，而是为了地图去使用 AI。**
- **不要先写数据库，先写 Navigation Session。**
- 导航即学习，学习即建图。
- 导航优先于执行，引导用户而非替代用户。

## 项目结构

```
digital-interaction-engine/
├── core/                   # 核心引擎
│   ├── session/                # Navigation Session（核心，最先开发）
│   ├── vision/                 # 视觉解析（OCR + 页面识别）
│   ├── hd_map/                 # 高精交互地图（Golden Flow + Node Match）
│   ├── learning/               # 交互学习（Interaction Flow + 地图成长）
│   └── voice/                  # 语音引导
├── data/                   # 数据层
│   ├── golden_flows/           # 已审核/可纠正的 Golden Flow
│   ├── live_training/          # 网页端实时训练数据（最高可信）
│   ├── candidate_flows/        # 未验证候选 Flow（最低可信，默认不加载）
│   ├── learned_flows/          # 旧学习产物目录（保留兼容）
│   ├── interaction_logs/       # 脱敏交互事件日志
│   ├── ontology/               # 本体定义
│   ├── raw_recordings/         # 原始录屏
│   └── processed/              # 处理后的帧数据
├── platform/               # 平台适配层
│   └── android/                # Android 屏幕采集
├── demo/                   # HTML 演示
├── tests/                  # 测试
├── scripts/                # 工具脚本
├── docs/                   # 项目文档
└── configs/                # 配置
```

## V1.0 目标

> 验证数字交互地图是否能够在真实导航过程中持续学习、持续成长。

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/00-project-context.md](docs/00-project-context.md) | 项目共识 V1.0 |
| [docs/01-architecture.md](docs/01-architecture.md) | 架构设计（以 Session 为中心） |
| [docs/02-data-model.md](docs/02-data-model.md) | 数据模型 |
| [docs/03-mvp-spec.md](docs/03-mvp-spec.md) | V1.0 开发规格 |
| [docs/04-roadmap.md](docs/04-roadmap.md) | 路线图 |
| [docs/05-training-pipeline.md](docs/05-training-pipeline.md) | iPhone 镜像采集与训练闭环 |
| [docs/06-click-capture-options.md](docs/06-click-capture-options.md) | 点击坐标采集方案 |
| [docs/07-training-handoff.md](docs/07-training-handoff.md) | 网页实时训练交接说明 |
