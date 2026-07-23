# 架构设计 V1.0

## 核心原则

**先写 Session，不先写数据库。**

产品核心是连续导航状态机（Navigation Session），不是数据库。数据库只是 Session 的知识来源。只要 Session 能跑起来，哪怕地图里只有 5 个节点，整个产品的交互就已经成立了。

## 以 Session 为中心的架构

```
┌──────────────────────────────────────────────────────────────────┐
│                     Navigation Session                           │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Session State Machine                    │ │
│  │                                                             │ │
│  │  IDLE -> TASK_RECOGNIZED -> NAVIGATING -> TASK_COMPLETE     │ │
│  │                                  │                          │ │
│  │                            ┌─────┴─────┐                    │ │
│  │                            │  LOOP:    │                    │ │
│  │                            │ observe   │                    │ │
│  │                            │ locate    │                    │ │
│  │                            │ navigate  │                    │ │
│  │                            │ learn     │                    │ │
│  │                            └───────────┘                    │ │
│  └────────────────────────────────────────────────────────────┘ │
└───────────────────────────┬──────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Vision       │    │  HD Map      │    │  Learning    │
│  (AI Layer)   │    │  (Ground     │    │  (Growing    │
│               │    │   Truth)     │    │   Map)       │
│  OCR          │    │              │    │              │
│  Screen       │    │  Golden Flow │    │  Interaction │
│  Analyzer     │    │  Node Match  │    │  Flow Record │
│  App Detect   │    │  Risk Check  │    │  Map Update  │
│  Version Adpt │    │  Next Node   │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

## Navigation Session 状态机

整个系统围绕一个 Session 运行：

```
                用户说目标
                    │
                    ▼
            ┌───────────────┐
            │  IDLE         │
            └───────┬───────┘
                    │ Task Recognition
                    ▼
            ┌───────────────┐
            │  ACTIVE       │
            │  task=refund  │
            │  app=taobao   │
            │  current_node │
            └───────┬───────┘
                    │
            ┌───────▼───────┐
            │               │
     ┌──────┴──────┐       │
     │  NAVIGATE    │◄──────┤  持续循环
     │              │       │
     │  1. observe   │       │
     │  2. locate    │       │
     │  3. navigate  │       │
     │  4. learn     │       │
     │              │       │
     └──────┬──────┘       │
            │               │
            │ 页面无变化     │
            │ ─────────────►│
            │               │
            │ 到达终点       │
            │               │
            ▼               │
     ┌──────────────┐       │
     │  COMPLETE    │       │
     │  保存 Flow   │       │
     └──────────────┘       │
            │               │
            ▼               │
     ┌──────────────┐       │
     │  地图成长    │       │
     └──────────────┘       │
                            │
```

### Session 核心数据结构

```python
class NavigationSession:
    session_id: str
    task: str                    # "refund", "contact_cs", "find_order"
    app: str                     # "taobao", "jd", "pdd"
    status: str                  # "idle", "active", "navigating", "complete"
    current_node: str            # 当前定位到的节点
    navigation_path: list        # 导航轨迹 [{node, action, timestamp, confidence}]
    golden_flow_id: str          # 使用的 Golden Flow
    interaction_events: list     # 交互事件记录
    started_at: datetime
    completed_at: datetime
```

### 导航循环（核心 Loop）

每一步执行四个动作：

```
1. OBSERVE
   - 获取当前屏幕截图
   - AI 识别页面内容（OCR + 组件识别）

2. LOCATE
   - 用 Golden Flow 匹配当前页面
   - 定位到 Node
   - 计算置信度

3. NAVIGATE
   - 从地图获取下一步信息
   - 检查风险点
   - 生成引导语
   - 语音播报

4. LEARN
   - 记录交互事件
   - 如果地图中没有当前 Node，标记为"未知节点"
   - 如果 AI 定位置信度低，记录待人工审核
```

## 模块职责

### Navigation Session（核心模块，最先开发）

- 管理 Session 生命周期
- 驱动导航循环
- 协调 Vision、Map、Learning 三个子系统
- 生成最终 Interaction Flow

### Vision（视觉解析）

- OCR：识别屏幕文字
- Screen Analyzer：分析屏幕布局
- App Detector：识别当前 App
- 版本适配：处理动态变化

### HD Map（高精交互地图）

- Golden Flow：预置的已知流程
- Node Match：将页面匹配到节点
- Risk Check：风险检测
- Next Node：下一步建议

### Learning（交互学习）

- Interaction Flow Record：记录导航轨迹
- Map Update：自动更新地图
- Unknown Node：发现未知节点
- Quality Gate：质量评估（置信度低于阈值时标记待审核）

## 数据流

```
用户: "我要退款"
    │
    ▼
Session: task = "refund"
    │
    ▼
Session: 查找 Golden Flow (退款)
    │
    ▼
┌─► Session.observe()
│   └─► Vision.ocr(screen)
│   └─► Vision.detect_app(screen)
│
├─► Session.locate()
│   └─► Map.match_node(ocr_result, flow)
│   └─► current_node = "order_detail"
│   └─► confidence = 0.94
│
├─► Session.navigate()
│   └─► Map.get_next_node(current_node, flow)
│   └─► Map.check_risk(next_node)
│   └─► "请点击'申请售后'按钮"
│   └─► Voice.speak(guidance)
│
├─► Session.learn()
│   └─► Learning.record_event(node, action, confidence)
│
└─► 等待页面变化...
    │
    └─► 回到 observe()
```

## 任务结束时

```
Session.complete()
    │
    ├─► 导出 Interaction Flow:
    │   task: refund
    │   app: taobao
    │   events: [
    │     {node: home, action: navigate_mine, duration: 3s, confidence: 0.95},
    │     {node: mine, action: click_orders, duration: 2s, confidence: 0.92},
    │     {node: order_list, action: find_order, duration: 5s, confidence: 0.88},
    │     ...
    │   ]
    │
    ├─► Learning.compare_with_golden_flow()
    │   ├─ 匹配的部分: 确认地图正确
    │   ├─ 偏差的部分: 记录异常路径
    │   └─ 缺失的部分: 记录新发现的节点
    │
    └─► Map.update(learning_result)
        └─ 地图成长
```

## 技术栈

| 模块 | 技术 | 说明 |
|------|------|------|
| Session 状态机 | Python asyncio | 异步事件循环，支持持续运行 |
| 视觉解析 | PaddleOCR + LLM API | OCR + 语义理解 |
| 地图存储 | SQLite（V1.0 轻量） | Golden Flow + 学习到的 Flow |
| 语音输出 | Edge-TTS | 文字转语音 |
| Android 平台 | ADB / Accessibility | 屏幕采集 |
| 数据采集 | 本地 JSON 日志 | 脱敏交互事件 |

## V1.0 开发顺序

1. **Navigation Session**（先）
2. **Golden Flow 数据**（最少可用）
3. **Vision 集成**（OCR + 页面识别）
4. **Learning 模块**（交互记录 + 地图更新）
5. **端到端 Demo**（连起来跑）
