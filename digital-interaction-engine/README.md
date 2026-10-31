# Digital Interaction Engine（数字交互引擎）

> 小路：面向中国中老年用户的连续手机操作导航。

## 一句话描述

小路是商业化手机导航产品。用户用文字或语音表达目标，系统持续识别实际页面，一次讲清一步，由用户自己操作，直到任务结束。当前优先 Android 和抖音。

**当前 Android 1.1.00**：GUI + 模型推理连续导航，不以预建完整地图为前提；移除 APK
无障碍/学习/训练入口，保留旧数据。独立授权后的结构化反馈进入服务器待审核候选，
不自动训练权重或发布地图。接入、运维和实际限制见 [1.1试用说明](docs/14-consumer-pilot-1.1.md)。
下列 Python 地图引擎说明主要保留为研究架构，不代表 Android 1.1已集成所有模块。

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

> 让目标用户可靠地独立完成受支持的手机任务，并验证付费需求与服务成本；通过审核过的真实交互持续改进导航。

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
| [docs/08-douyin-apk-static-analysis.md](docs/08-douyin-apk-static-analysis.md) | 抖音 APK 静态分析与 Golden Flow 交叉验证 |
| [docs/09-mobile-package-static-analysis.md](docs/09-mobile-package-static-analysis.md) | 常用 App 安装包静态分析流水线与边界 |
| [docs/13-approved-app-static-evidence.md](docs/13-approved-app-static-evidence.md) | 本批8个App的静态图册、存储与暂缓范围 |
| [docs/10-common-app-package-baseline.md](docs/10-common-app-package-baseline.md) | 十个常用 App 的 Android 静态基线与 iOS 验证矩阵 |
| [docs/12-douyin-apk-flow-atlas.md](docs/12-douyin-apk-flow-atlas.md) | 抖音 40.3.0 流程证据图册、扫描结果与未解析边界 |
