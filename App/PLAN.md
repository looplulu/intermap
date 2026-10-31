# InterMap Android App 完整开发计划

> 历史 1.0.x 方案。本版无障碍训练已退出 APK；当前 1.1.00 实现与限制见
> `../digital-interaction-engine/docs/14-consumer-pilot-1.1.md`。不要按本文恢复无障碍入口。

## 一、技术选型

### 框架：Flutter
- **理由**：`flutter_accessibility_service` 插件现成可用，支持事件监听、节点操作、Overlay悬浮窗；`flutter_tts` 成熟稳定；MethodChannel 可桥接截屏等自定义原生能力
- **APK打包**：`flutter build apk --release`，一条命令

### 核心原生能力组合
1. **AccessibilityService** — 结构化事件捕获（点击、文本变化、页面切换、滚动）
2. **MediaProjection / ScreenCapture API** — 像素级屏幕截图（用于视觉分析/OCR）
3. **System Alert Window** — 悬浮窗覆盖层，在目标App上方显示引导提示
4. **Android TTS** — 语音播报

---

## 二、架构重新设计（与网页端的核心差异）

### 2.1 事件采集层：从"录屏OCR"到"无障碍事件流"

```
网页端：  屏幕录制 → 定时抽帧(1.5s) → OCR → 文本匹配 → 判断页面/操作
Android：AccessibilityService → 事件回调(实时) → 节点树解析 → 直接获取控件信息
```

**AccessibilityService 能直接获取的信息**：
- 控件文本（`getText()`）
- 控件描述（`getContentDescription()`）
- 控件类型/类名（`getClassName()`，如 `android.widget.Button`）
- 控件ID（`getViewIdResourceName()`，如 `com.ss.android.ugc.aweme:id/btn_like`）
- 屏幕位置（`getBoundsInScreen()`，返回矩形区域）
- 是否可点击/可滚动/已勾选
- 整个窗口的控件树（`getRootInActiveWindow()`）

**这意味着**：
- 不需要每1.5秒OCR来判断页面——`TYPE_WINDOW_STATE_CHANGED` 直接告诉你页面切换了
- 不需要通过OCR文本来推断用户点了什么——`TYPE_VIEW_CLICKED` 直接告诉你哪个控件被点了
- 控件ID比OCR文本更稳定（不受字体/颜色/背景影响）

### 2.2 新架构分层

```
┌─────────────────────────────────────┐
│         Flutter UI Layer             │  主界面、设置、任务选择
├─────────────────────────────────────┤
│      Navigation Engine (Dart)       │  状态机、引导升级、迷失检测
│      (从Python引擎移植核心逻辑)       │
├──────────────┬──────────────────────┤
│ Accessibility │  Screen Capture     │  原生能力层
│ Service       │  (MediaProjection)  │
│ (事件+控件树) │  (视觉截图)         │
├──────────────┴──────────────────────┤
│         MethodChannel Bridge         │  Flutter ↔ 原生通信
├─────────────────────────────────────┤
│       Golden Flow / Task Data        │  JSON 本地数据
└─────────────────────────────────────┘
```

---

## 三、权限解决方案

### 必需权限
- 无障碍服务（核心）
- 悬浮窗 `SYSTEM_ALERT_WINDOW`（引导覆盖层）
- `FOREGROUND_SERVICE` + `FOREGROUND_SERVICE_MEDIA_PROJECTION`（截屏）
- `INTERNET`（API调用）

### Android 13+ "受限制的设置"问题
侧载APK无障碍开关会灰色，需引导用户去「应用详情 → 允许受限制的设置」解锁。

---

## 四、开发阶段

### Phase 1：基础框架搭建
### Phase 2：核心导航引擎移植
### Phase 3：抖音退货场景打通
### Phase 4：训练系统
### Phase 5：扩展训练（持续）

详见上轮对话的完整计划。
