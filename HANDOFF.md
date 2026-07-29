# 小路（InterMap）项目交接文档

## 一、项目概述

**小路**是一个面向中老年人的数字世界导航 App，帮助用户完成手机 App 操作（如抖音退款、淘宝下单等）。通过截屏/GUI识别或无障碍服务，实时理解用户当前所处页面，用语音引导下一步操作。

**项目根目录**：`/Users/assum/projects/intermap`
**Flutter App 目录**：`/Users/assum/projects/intermap/App`
**网页端 Demo / 数据工作台**：`/Users/assum/projects/intermap/digital-interaction-demo/`
**Python 引擎**：`/Users/assum/projects/intermap/digital-interaction-engine/`

---

## 二、产品架构决策（用户明确要求）

### 2.1 双模式架构

| 模式 | 技术 | 用户权限体验 | 当前状态 |
|------|------|-------------|---------|
| **录屏模式（默认）** | MediaProjection 截屏 + UI-TARS API 识别 | 系统弹窗点"允许"即可 | ✅ 已实现，调试点 |
| **无障碍模式** | AccessibilityService 读取 UI 树 | 需手动到设置开启，较麻烦 | ✅ 代码保留，独立测试模块 |
| **双模式（未来）** | 无障碍做触发器 + 录屏做视觉校正 | 两者都开 | 🔜 后续再考虑 |

**用户原话**："我们默认会采用录屏的模式，这样大家使用起来会更方便。同时我们在设置里是保留无障碍的选项的。"

**用户原话**："无障碍能够第一时间发现页面产生了变化，因为它知道用户点了什么。所以不需要像单一录屏模式下需要频繁的快速的去进行屏幕识别。无障碍本身勾勒出了一个基本的情况，但可能不是很准确（比如微信会篡改无障碍节点内容），所以同时也要用录屏的GUI识别做一个校正。"

**用户原话**："等这波测试都完成之后，后续怎么弄到时候再说。"

### 2.2 APK 版本命名规则

格式：`小路{大版本}.{功能序号}.{调试序号}.apk`

- 同一功能调试递增最后两位：`小路1.0.00.apk` → `小路1.0.01.apk` → `小路1.0.02.apk`
- 换新功能：`小路1.1.00.apk` → `小路1.1.01.apk`
- 大版本迭代（2.0）由用户决定

当前最新：`小路1.0.08.apk`

### 2.3 GitHub 阶段备份规则

用户要求：之后每完成一个阶段性任务，就把代码上传到 GitHub 仓库 `looplulu/intermap`，按上传时的版本号命名，作为备份留存。GitHub 上只保留最近两个备份版本：最新一次和上一次；更早的版本在新备份确认成功后删除。

阶段性任务标准由 Codex 自主判断，建议按以下口径执行：

- 生成了一个可安装、可验证的新 APK 版本；
- 线上 `intermap` 子站完成一轮可用功能部署；
- 训练数据结构、采集链路、后端接口完成一轮闭环；
- 重要文档/交接内容已经同步到能支撑下一阶段开发。

上传命名建议：

- 版本分支：`snapshot/xiaolu-1.0.08`
- 版本标签：`xiaolu-1.0.08`
- 提交信息：`小路1.0.08 阶段备份`

执行原则：

- 不 force push，不覆盖已有同名分支或标签；
- 如果同名版本已经存在，先提升调试版本号，例如 `1.0.08`；
- 新备份成功后，检查 `snapshot/xiaolu-*` 分支和 `xiaolu-*` 标签，只保留版本号最新的两个，其余远端分支和标签删除；
- 上传源码、文档、必要静态资源，不上传 `App/build/`、`.dart_tool/`、APK、训练原始视频、数据库、本地环境配置；
- 根目录 `.gitignore` 是当前备份边界，上传前必须再检查一次 `git status`。

---

## 三、当前 App 结构

### 3.1 首页双链路入口

```
小路 - 数字世界导航
├── 录屏 GUI → 实际导航测试演示 / 我实际操作进行学习 / 我提出目标进行导航并反馈
└── 无障碍 → 开启无障碍权限 → 实际导航测试演示 / 我实际操作进行学习 / 我提出目标进行导航并反馈
```

当前优先打磨抖音。演示页固定使用 `douyin`，训练页默认填写 `douyin`，其它 App 暂不作为主路径。

### 3.2 关键文件清单

#### Dart 代码（`App/lib/`）

| 文件 | 作用 |
|------|------|
| `main.dart` | App 入口、所有 UI 页面、AppViewModel（状态管理） |
| `services/screen_capture_service.dart` | 录屏管理器 + UI-TARS API 客户端 + 帧变化检测器 |
| `services/screen_nav_session.dart` | 录屏导航会话：截帧→去重→API→语音引导→卡住升级 |
| `services/guidance_style.dart` | 导航话术整理：简洁/详细模式和模型输出口语化 |
| `services/accessibility_manager.dart` | 无障碍事件管理（绕过插件静态Stream，自建EventChannel） |
| `services/navigation_session.dart` | 无障碍导航会话：事件→HDMap匹配→引导 |
| `services/training_session.dart` | 训练/学习会话管理 |
| `services/tts_service.dart` | TTS 语音播报（flutter_tts） |
| `services/hd_map.dart` | Golden Flow 匹配引擎（关键词加权评分） |
| `models/golden_flow.dart` | Golden Flow 数据模型（FlowNode, FlowEdge, Guidance, Risk） |
| `models/accessibility_event.dart` | 无障碍事件数据模型 |
| `models/nav_event.dart` | 导航事件/步骤模型 |
| `data/douyin_refund_flow.dart` | 抖音退款 Golden Flow 数据（硬编码） |

#### Android 原生代码（`App/android/app/src/main/kotlin/com/intermap/intermap_app/`）

| 文件 | 作用 |
|------|------|
| `MainActivity.kt` | MethodChannel + EventChannel 桥接，处理录屏权限请求 |
| `ScreenCaptureService.kt` | MediaProjection 前台服务：VirtualDisplay + ImageReader 截屏，base64 JPEG 回传 Dart |

#### Android 配置

- `AndroidManifest.xml`：注册了 `ScreenCaptureService`（foregroundServiceType=mediaProjection）和无障碍服务
- `gradle/wrapper/gradle-wrapper.properties`：Gradle 9.6.1
- `settings.gradle.kts`：AGP 9.0.1, Kotlin 2.3.20
- `gradle.properties`：`android.enableJdkImageTransform=false`

### 3.3 导航话术

- 默认使用“简洁”模式，只播报点击目标和位置；
- 可在演示导航开始页切换为“详细”模式；
- 详细模式使用“当前是……，点击……，就会进入……”的自然表达；
- UI-TARS 返回的“页面名：……，操作：……”只作为结构化识别结果，不再原样朗读；
- 录屏 GUI 和无障碍两条导航链路共用同一话术设置。

### 3.4 MethodChannel / EventChannel

| Channel | 类型 | 用途 |
|---------|------|------|
| `com.intermap/app` | MethodChannel | `moveToBackground`、`requestScreenCapture`、`stopScreenCapture` |
| `com.intermap/capture_event` | EventChannel | 截屏帧 base64 JPEG 流 |
| `x-slayer/accessibility_event` | EventChannel | 无障碍事件流（自建，非插件） |

---

## 四、技术链路

### 4.1 录屏模式导航流程

```
用户点"开始导航"
  → 系统弹出 MediaProjection 授权弹窗
  → 用户授权
  → 启动 ScreenCaptureService（前台服务 + 音频焦点）
  → App 退到后台（moveTaskToBack，不销毁 Activity）
  → ImageReader 持续捕获屏幕帧
  → base64 JPEG 通过 EventChannel 传到 Dart
  → FrameChangeDetector 帧哈希去重 + 1.5秒间隔控制
  → UiTarsClient.analyze() POST 到 API
  → 解析返回的 action/thought → TTS 语音播报
  → 卡住检测：8秒无新引导自动升级（3级）
```

### 4.2 API 调用

**端点**：`https://loop-lulu.com/intermap/api/ui-tars`

**请求格式**：
```json
{
  "image": "data:image/jpeg;base64,{base64Frame}",
  "task": "用户的目标是: \"{task}\"。请识别当前页面，判断用户在完成目标过程中的哪一步。",
  "history": []
}
```

**返回格式**：
```json
{
  "ok": true,
  "thought": "AI思维链",
  "action": "建议操作",
  "action_type": "click",
  "point": {"x": 500, "y": 300},
  "modules": [...]
}
```

### 4.3 无障碍模式导航流程

```
用户开启无障碍服务
  → AccessibilityServiceManager.startListening()
  → 自建 EventChannel('x-slayer/accessibility_event') 接收事件
  → 解析 JSON：eventType, packageName, capturedText, subNodesActions
  → NavigationSession.handleAccessibilityEvent()
  → HDMap.match_node() 关键词匹配
  → 匹配到节点 → 输出引导 → TTS 播报
  → 卡住检测 + 迷失检测
```

### 4.4 Golden Flow 匹配算法

- 每个 FlowNode 有 `key_indicators`（关键词列表）
- 全文匹配，强指示词（≥3字符）权重 60%，全部指示词权重 40%
- 阈值 ≥ 0.3 才认为匹配

---

## 五、编译环境

```bash
# 必须用 Java 17（系统默认 Java 26 与 Gradle/AGP 不兼容）
export JAVA_HOME="/opt/homebrew/Cellar/openjdk@17/17.0.19/libexec/openjdk.jdk/Contents/Home"

# 编译
cd /Users/assum/projects/intermap/App
flutter build apk --debug

# 复制到桌面（按版本命名）
cp build/app/outputs/flutter-apk/app-debug.apk ~/Desktop/小路1.0.{XX}.apk

# 清理
flutter clean
```

**关键**：
- Java 17 通过 `brew install openjdk@17` 安装
- Gradle 9.6.1 + AGP 9.0.1 + Kotlin 2.3.20
- `jni` 和 `jni_flutter` 插件的 `compileSdk` 已从 35 改为 36（在 pub-cache 中修改）

---

## 六、当前调试状态

### 已完成
- ✅ 录屏模式：MediaProjection 截屏 → API 识别 → 导航记录显示
- ✅ 无障碍模式：事件捕获（绕过插件 Stream bug）→ HDMap 匹配 → 引导
- ✅ 三模块 UI：演示模式、训练模式、无障碍测试
- ✅ 训练模式：录制 + 标注 + 上传到服务器
- ✅ 抖音退款 Golden Flow 数据
- ✅ App 后台保持运行（moveTaskToBack 替代 SystemNavigator.pop）
- ✅ 前台 Service 音频焦点（解决后台 TTS 不发声）
- ✅ Android 启动器图标与 App 首页 logo 已替换为小路正式 logo（`小路1.0.04.apk`）
- ✅ 无障碍插件 overlay entrypoint 已补齐，避免后台 Flutter engine 报 `Could not resolve main entrypoint function`（`小路1.0.05.apk`）
- ✅ 录屏截帧已在原生层节流并回收 Bitmap，降低真机录屏时的 GC/压缩压力（`小路1.0.06.apk`）
- ✅ 首页已改为“录屏 GUI / 无障碍”双链路，每条链路都有导航演示、自由学习、目标反馈训练三种模式（`小路1.0.07.apk`）
- ✅ 录屏训练已接入：MediaProjection 截帧 → UI-TARS 页面观察 → TrainingSession 记录节点/事件/人工标注 → 上传服务器（`小路1.0.07.apk`）
- ✅ App 内 logo 与 Android launcher 图标已替换为 `/Users/assum/Pictures/小路/logo.jpg`，图标保留更多留白避免过大（`小路1.0.07.apk`）
- ✅ TTS 调整为更柔和的语速/音调，并在原生 Android 侧优先选择中文高质量/女声倾向 voice（`小路1.0.07.apk`）

### 当前问题（待解决）

1. **录屏模式语音待真机复测**
   - `小路1.0.02.apk` 已加入 Android 原生 TextToSpeech 兜底
   - Android 上优先走原生 TTS，失败再回退到 flutter_tts
   - 仍需在真机录屏后台状态下确认是否稳定出声

2. **录屏训练需真机复测数据质量**
   - `小路1.0.07.apk` 已能把录屏识别结果写入 TrainingSession
   - 需要在抖音真机操作中确认 UI-TARS 返回的 `thought/action/texts` 是否足够生成稳定节点
   - 若返回文本不足，下一步应调整 `/intermap/api/ui-tars` 的 prompt/返回结构，让后端明确输出 `texts` / `key_texts` / `page_type`

3. **重新打开 App 回到首页**
   - 已修复（改用 moveTaskToBack），但需验证

### 已知的历史 bug 修复记录

- `SystemNavigator.pop()` 会销毁 Activity → 改用 `moveTaskToBackground`
- 插件 `accessStream` 是 static 缓存，第二次 listen 不触发 Java onListen → 自建 EventChannel
- 插件传的是 JSON 字符串不是 Map → 增加 jsonDecode
- Java 26 与 Gradle 9.1.0 不兼容 → 升级到 Gradle 9.6.1
- `jni` 插件 compileSdk 35 在 Android 36 上 jlink 失败 → 改为 36
- 空包名事件被丢弃 → 改为标记 'unknown' 并继续处理

---

## 七、网页端 / Python 引擎参考

### 7.1 网页端 Demo（`digital-interaction-demo/index.html`）

- 截帧频率 1.5 秒（训练模式 200ms）
- 图像预处理：缩放到 900-1400px 宽度 + 灰度对比度增强（1.45x）
- 输出 JPEG 质量 0.82-0.85
- 帧哈希去重：每 4 像素采样
- 卡住阈值 8 秒，3 级升级
- 迷失检测：30 秒窗口内 A→B→A→B 振荡 3 次

### 7.2 Python 引擎（`digital-interaction-engine/`）

- `core/hd_map/map.py`：Golden Flow 匹配
- `core/session/page_change.py`：页面变化检测（Jaccard 相似度，阈值 0.25-0.3）
- `core/vision/llm_client.py`：DeepSeek V4 Flash fallback
- `core/vision/ocr.py`：PaddleOCR 中文版
- `data/golden_flows/`：淘宝退款、京东退款、淘宝订单、微信视频号购物
- `data/candidate_flows/unverified_web/`：50+ 待验证的 Web 流程

### 7.3 网页端 API 端点

| 端点 | 用途 |
|------|------|
| `/intermap/api/ui-tars` | UI-TARS 视觉识别（Demo 模式主力） |
| `/api/analyze` | 上传图片文件分析 |
| `/api/analyze_base64` | base64 图片分析 |
| `/api/understand` | OCR + LLM 理解 |

---

## 八、用户核心要求汇总

1. **默认录屏模式**：用户体验好，权限弹窗点一下就行
2. **无障碍保留为测试模块**：手动开启，用于打磨，不是产品功能
3. **三个模块**：演示（录屏）、训练（录屏）、无障碍测试
4. **APK 版本命名**：`小路{大版本}.{功能序号}.{调试序号}.apk`
5. **GUI 识别复用网页端链路**：同一 API key，同一模型（UI-TARS），做手机端微调
6. **双模式是未来方向但不是现在**：先把录屏跑通，无障碍作为增强后续再说
7. **当前 APK 是内部打磨版**：不是产品，功能跑通后再整合到产品中的合适位置

## 九、Looplulu Intermap 子站新定位

`https://loop-lulu.com/intermap/` 不再作为主训练入口。

新的优先级：

1. Android / iOS App 真机实时训练是主数据源。
2. Intermap 子站保留为演示复盘、镜像窗口补充采集、API 调试和人工标注工作台。
3. 任何会写入后台训练数据、Session、标注或 review 数据的操作，都必须先通过密码验证。
4. 网页端补充采集不得覆盖 App 真机训练数据；数据可信度低于 App 真机实时训练。

---

## 十、下一步建议

1. **优先修复 TTS 语音问题**：验证音频焦点是否生效，必要时用 `await` 确保 TTS 初始化完成
2. **录屏训练模式**：为训练模式实现截帧录制 + 画面变化检测 + 标注流程
3. **验证 API 响应质量**：检查 UI-TARS API 返回的 action/thought 是否合理，prompt 是否需要调整
4. **Golden Flow 接入录屏模式**：当前录屏模式纯靠 API 推理，可以考虑先用 Golden Flow 匹配（通过 API 返回的页面文本），匹配失败再 fallback 到纯 AI 引导
5. **App 后台返回时的状态恢复**：确保从后台切回来时能看到导航进度
