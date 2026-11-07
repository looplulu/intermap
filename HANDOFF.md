# 小路（InterMap）项目交接文档

## 官网阶段 1.1.01

2026-10-31 官网首页改为产品介绍、三步交互示意、当前试用场景、试用说明和常见问题。
原首页迁到 `/intermap/workbench.html`，旧采集复盘仍为 `/intermap/training-review.html`。
保留现有密码保护和全部训练/反馈数据；本次不修改 App，不重新生成 APK。
已交付试用包仍为 1.1.00，官网阶段号见 `digital-interaction-demo/VERSION`。
源码、后续更新与整目录替换部署见 `digital-interaction-demo/README.md`。

## 当前：1.1.04 四秒提醒与共享恢复

2026-11-07：从语音真实播放结束开始计时，同页安静4秒后最多自动提醒一次；
同页模型换句话不立即重播。新画面仍待识别时不冒险重复旧操作。
黑屏改为recovering，不调用stopScreenCapture，保留任务和本地帧监听；可见画面返回后接续。
用户截图确认vivo“屏幕共享保护→隐私应用保护”，截图中此项关闭，不能再要求重复关闭。
共享设置优先处理，购物渠道明确走该渠道订单；不明确且微信付款可查账单来源，找到账单不是退货完成。
速度基准：同一自有Logo短任务，豆包3937/3827ms；DeepSeek Flash与GLM Flash返回ModelNotOpen。
未配置新模型、未实现端侧OCR或视频结构分离、没有1秒有效导航保证。

## 1.1.03 退出、黑屏及语速修正

2026-11-05 已查到用户17:26至17:28的1.1.02测试：15次视觉观察，完成反馈已上传。
云端推理5.398至8.434秒，中位数7.447秒；1秒内有效导航未达标，不能用“正在识别”充数。
本次增加常显结束按钮、疑似完成先暂停再弹窗、近黑画面3秒暂停及条件式授权/隐私说明。
原生TTS语速改用Flutter参数的2倍，音调恢复1.0，避免0.46倍速造成拖腔。
短两行输出试验仍需8.43秒，已撤回，保留原结构化输出。视频页面仍按JPEG变化发请求，尚无本地结构/OCR检测，
亚秒响应和可靠的视频/布局分离仍是未完成项。见14号文档，不应对外宣称已达标。

## 1.1.02 通用文案与语音防打断

2026-11-01：输入提示、完成确认、设置和分享说明不再使用抖音订单或退款示例。
任务导航面向各App和系统页面，后端允许实际App标识；不表示所有App已经验收。
GUI返回稳定的page_key，同页数字/视频/文字波动不应改变身份。原生TTS报告真实播放结束，
同页更新只保留最新待播指导，结束后再播；换页且话术变化才允许打断。用户主动暂停/结束/重听不受限制。
数据收集上传、密码保护与新旧数据隔离保留；旧版抖音地图源码仍为历史资料，不在主入口调用。

## 1.1.00 联网试用版

2026-10-31 用户确认改为 GUI + 模型推理的连续任务导航，先获得市场反馈，不再要求先建完整地图。
APK 已重做消费者入口：文字/系统语音输入、可拖动悬浮任务入口、连续语音指导、暂停/重听/纠错/完成确认。
移除 APK 无障碍服务和学习/训练入口。旧训练数据保留，旧队列不由新版继续上传。
用户单独同意后，结构化观察、纠错、技术异常与任务结果自动传入 `consumer_feedback_v1`，
手机反馈有私有暂存和24小时内补传，服务重启后仍可接受反馈。模型推测与真实点击明确区分，
不自动发布 Golden Flow、不自动训练权重。线上模型主路为现有 ARK 视觉模型；生产未配置 DeepSeek。

交付与已知限制详见 `digital-interaction-engine/docs/14-consumer-pilot-1.1.md`。
不等待手机连接，按用户要求交付侧载试用包；构建、接口和自动测试不等于 vivo 真机通过。
实际声音、系统语音输入、悬浮窗和抖音任务延迟仍由用户安装后验证。

**下面 1.0.x 的无障碍训练与地图优先架构保留为历史，不再是当前 APK 说明。**

## 历史：1.0.19 任务完成确认

无障碍“训练模式”填写目标后，进入目标 App 会显示可拖动的“任务完成”悬浮按钮。
操作者看到预期结果时点击，手机先写入 `task_outcome` 原始事件（`user_confirmed_completed`，
证据级别 `user_report_only`，关联最近操作和画面），再结束采集并继续上传。
自由探索的学习模式没有目标，不显示按钮。普通“结束”不记为任务完成。
服务器复盘页显示确认和附近画面；该确认不自动将 Golden Flow 标记为已验证。
先确认旧版未上传数据已补传，再安装 `小路1.0.19.apk`。新版尚需 vivo 真机验收。

## 1.0.18 真机采集更新（优先于下面旧版采集说明）

目标手机：用户的 **vivo Y300 Pro**。新版以原生无障碍事件和录屏画面形成证据，
采集不等待 GUI 返回。无障碍提供来源控件范围，不是原始手指触点；后端用操作前画面裁剪目标，
结合前后 GUI/OCR 分析生成待审核交互材料。

新数据单独存储于 `/var/www/intermap-data/android_training_v3/`；旧 `training_sessions/` 不覆盖、不混入。
新增私有复盘页面：`https://loop-lulu.com/intermap/training-review.html`，所有数据读取和写入均需现有训练密码。
后台服务为 `intermap-capture.service`，原始材料上传完成后自动整理候选，尚不自动发布 Golden Flow 或训练模型权重。

完整操作步骤、实际采样限制、文件协议和后续审核见 `digital-interaction-engine/docs/11-android-training-v3.md`。
本次无 ADB 真机连接，构建与自动化测试不等同 vivo 实测；首次安装需重新确认新小路无障碍服务。

## 一、项目概述

**小路**是面向中国中老年智能手机用户的商业产品。用户通过文字或语音表达目标，系统以屏幕视觉识别为主，连续播报一步一步的操作指导，用户自行操作，系统在页面变化后继续引导和纠错。无障碍用于训练和兜底。

**2026-09-10 定位更新（优先于早期规划）**：项目已不以比赛或公益项目为定位，需要验证付费需求、获客、留存和单位服务成本。文字目标输入与语音输入同等重要，方言识别失败时必须允许用户用文字表达或修正。默认简洁播报，保持用户操作权，不通过自动点击来解决用户任务。“老人端免费、机构付费”仅作为商业假设，尚未确定价格或收费对象。

**导航依据**：通过系统化、大量的真实手机操作采集构建可靠交互地图，已审核且适用的地图是任务路径规划的主要依据。GUI 负责识别当前状态、定位实际入口，GUI 与推理共同适配不同系统、手机、App 版本和临时页面。实际流程与地图不符时重新定位或形成候选变体，经验证后更新地图。视觉主路指感知方式，不代表每一步都依靠模型重新推理路径。

上述为产品要求，并不表示已全部实现。当前 Android 原型有文字任务输入和 TTS；独立语音目标输入、完整任务状态机及审核后地图发布闭环仍需实现或验收。最新产品共识见 `digital-interaction-engine/docs/00-project-context.md`。

**项目根目录**：`/Users/assum/projects/intermap`
**Flutter App 目录**：`/Users/assum/projects/intermap/App`
**网页端 Demo / 数据工作台**：`/Users/assum/projects/intermap/digital-interaction-demo/`
**Python 引擎**：`/Users/assum/projects/intermap/digital-interaction-engine/`

---

## 二、产品架构决策（用户明确要求）

### 2.1 双模式架构

| 模式 | 技术 | 用户权限体验 | 当前状态 |
|------|------|-------------|---------|
| **演示模式** | MediaProjection 截屏 + UI-TARS API 识别 | 系统弹窗点"允许"即可 | ✅ 纯 GUI 连续导航 |
| **无障碍训练** | AccessibilityService 精确事件 + GUI 页面识别 | 需开启无障碍并允许录屏 | ✅ 学习与训练联合采集 |

**用户原话**："我们默认会采用录屏的模式，这样大家使用起来会更方便。同时我们在设置里是保留无障碍的选项的。"

**用户原话**："无障碍能够第一时间发现页面产生了变化，因为它知道用户点了什么。所以不需要像单一录屏模式下需要频繁的快速的去进行屏幕识别。无障碍本身勾勒出了一个基本的情况，但可能不是很准确（比如微信会篡改无障碍节点内容），所以同时也要用录屏的GUI识别做一个校正。"

**用户原话**："等这波测试都完成之后，后续怎么弄到时候再说。"

### 2.2 APK 版本命名规则

格式：`小路{大版本}.{功能序号}.{调试序号}.apk`

- 同一功能调试递增最后两位：`小路1.0.00.apk` → `小路1.0.01.apk` → `小路1.0.02.apk`
- 换新功能：`小路1.1.00.apk` → `小路1.1.01.apk`
- 大版本迭代（2.0）由用户决定

当前版本：`小路1.1.00.apk`（纯视觉任务导航联网试用，见文首）；下列为历史版本说明。

`1.0.17` 以已验证速度正常的 `1.0.08` 为视觉链路基线：演示模式仅依赖
MediaProjection 录屏和 GUI 视觉模型，截图缩小一半并使用 JPEG 65，模型只生成
页面名和下一步操作两行短结果。保留后续增加的页面身份稳定与语音去重，避免
同一页面反复打断。服务端 OCR 不进入首句引导的同步路径；无障碍仅用于独立的
学习/训练入口和未来兜底，不作为演示导航主路。

`1.0.17` 修复同一页面可见文字变化被错误抑制的问题：GUI 连续两帧识别到新的
目标文字后会更新引导，地图只决定目标位置和语义，播报必须采用当前画面的实际
文字。引导统一先说位置，再说点击对象，最后按需描述图标外观。

抖音退货路径固定为：抖音首页 → 个人主页 → 第一个“我的订单” → 商城页左上角
第二个“我的订单” → 用户在全部订单页自行选择要退货的商品 → 订单详情 → 申请退款。
“退款/售后”只用于查看已申请的售后，绝不能作为发起退货的入口。
简洁语音也必须说清目标方位和可见文字，有图标时再描述外观。App 复用 HTTPS 连接，视觉
取帧间隔从 500ms 调整为 300ms。

2026-09-03 使用抖音官网提供的 40.3.0 官方 APK 做了静态交叉验证。结果支持
“全部订单 -> 选择商品 -> 订单详情 -> 申请退款”这段主路径，同时证实订单
页结构和可见文字大量由服务端动态下发。详见
`digital-interaction-engine/docs/08-douyin-apk-static-analysis.md`。该类证据标记为
`apk_static`，优先级低于真机实时训练和录屏证据，不得自动覆盖 Golden Flow。

2026-09-04 完成微信、抖音、快手、小红书、淘宝、京东、拼多多、美团、
美团外卖和淘宝闪购的 Android 安装包静态基线，以及对应 iOS App Store 官方
元数据建档。服务器原始包和报告位于
`/var/www/intermap-data/package_static/`，分析工具位于
`/var/www/intermap-package-lab/`。iOS 不绕过 FairPlay，只通过真机或镜像补全
节点；完整版本矩阵和审核规则见
`digital-interaction-engine/docs/10-common-app-package-baseline.md`。

### 2.3 GitHub 阶段备份规则

用户要求：之后每完成一个阶段性任务，就把代码上传到 GitHub 仓库 `looplulu/intermap`，按上传时的版本号命名，作为备份永久留存。不再自动删除任何历史版本。

阶段性任务标准由 Codex 自主判断，建议按以下口径执行：

- 生成了一个可安装、可验证的新 APK 版本；
- 线上 `intermap` 子站完成一轮可用功能部署；
- 训练数据结构、采集链路、后端接口完成一轮闭环；
- 重要文档/交接内容已经同步到能支撑下一阶段开发。

上传命名建议：

- 版本分支：`snapshot/xiaolu-1.0.09`
- 版本标签：`xiaolu-1.0.09`
- 提交信息：`小路1.0.09 阶段备份`

执行原则：

- 不 force push，不覆盖已有同名分支或标签；
- 如果同名版本已经存在，先提升调试版本号，例如 `1.0.08`；
- 新备份成功后，检查 `snapshot/xiaolu-*` 分支和 `xiaolu-*` 标签均已上传，不删除任何历史版本；
- 上传源码、文档、必要静态资源，不上传 `App/build/`、`.dart_tool/`、APK、训练原始视频、数据库、本地环境配置；
- 根目录 `.gitignore` 是当前备份边界，上传前必须再检查一次 `git status`。

---

## 三、当前 App 结构

### 3.1 首页双链路入口

```
小路 - 数字世界导航
├── 演示模式 → 纯 GUI 连续导航
└── 无障碍 → 开启无障碍权限 → 学习 / 训练（无障碍 + GUI 联合采集）
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
- 页面身份采用规范化页面名去重；轻微 OCR 波动不重播，真正的新页面
  首次识别成功后立即切换引导。
- 演示模式自动上传脱敏诊断事件，包括接口状态、耗时、页面名、动作类型
  和播报决策；不上传截图、完整 OCR 内容或用户目标。服务端路径为
  `/var/www/intermap-data/navigation_diagnostics/`。

### 3.4 Android 训练数据闭环

- 学习和目标反馈训练均记录完整规范事件，而不是只上传摘要；
- 联合采集时，无障碍保存准确的点击类型、控件文字和 `viewId`，GUI 保存
  页面画面识别；准确操作会作为后续页面跳转的高可信动作证据；
- 会话在 App 私有目录持续保存，不保存截图或视频；
- 结束训练后自动上传，离线或失败数据会在下次训练密码验证后重试；
- 同一 `session_id` 重传会覆盖服务器旧副本，不会重复累计；
- 服务端原始会话位于 `/var/www/intermap-data/training_sessions/`；
- 单会话审核材料位于 `/var/www/intermap-data/review_queue/`；
- 跨会话候选地图位于 `/var/www/intermap-data/interaction_maps/`；
- 候选地图会汇总新旧数据并保留来源可信度，只有人工审核后才能进入
  Golden Flow。

### 3.5 MethodChannel / EventChannel

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
  "page_name": "抖音订单详情",
  "page_key": "稳定页面标识",
  "ocr_texts": ["退款金额", "49.8"],
  "amounts": ["49.8"]
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
