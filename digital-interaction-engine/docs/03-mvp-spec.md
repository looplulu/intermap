# V1.0 开发规格

> 历史规划，不是当前开发待办。1.1改为先试用 GUI + 推理导航，再积累可核实反馈；
> 当前范围与已实现能力见 [1.1试用说明](14-consumer-pilot-1.1.md)。

## 唯一目标

验证数字交互地图是否能够在真实导航过程中持续学习、持续成长。

## 开发顺序（严格按此顺序）

### 第一步：Navigation Session

先写 Session，不先写数据库。

Session 是整个系统的骨架。只要 Session 能跑起来，哪怕地图里只有 5 个节点，整个产品的交互就已经成立了。

**交付物：**
- `core/session/session.py` — Session 状态机
- `core/session/state.py` — Session 状态定义
- `core/session/event.py` — 交互事件定义
- 状态转换：IDLE -> ACTIVE -> NAVIGATING -> COMPLETE
- 导航循环：observe -> locate -> navigate -> learn

**验证标准：**
- Session 可以创建、启动、运行循环、完成
- Session 可以记录每一步的导航轨迹
- Session 完成时可以导出 Interaction Flow

### 第二步：Golden Flow（最小可用）

不追求完整地图。只建立淘宝退款的主流程 Golden Flow（5-8 个节点），用 JSON 文件存储。

**交付物：**
- `data/golden_flows/taobao_refund.json` — 淘宝退款主流程
- 每个节点包含：page_type、key_indicators、guidance、risks、next_node

**验证标准：**
- Session 可以加载 Golden Flow
- Session 可以根据 Golden Flow 判断当前页面匹配哪个节点

### 第三步：Vision 集成

将 OCR 和页面识别接入 Session 的 observe 和 locate 步骤。

**交付物：**
- `core/vision/ocr.py` — PaddleOCR 封装
- `core/vision/screen_parser.py` — 屏幕解析（OCR + 组件提取）
- `core/vision/app_detector.py` — App 识别

**验证标准：**
- 给一张截图，能返回 OCR 结果
- 给一张截图，能匹配到 Golden Flow 中的节点

### 第四步：Learning 模块

在 Session 的 learn 步骤中记录交互事件，任务结束时自动生成 Flow。

**交付物：**
- `core/learning/flow_recorder.py` — 交互事件记录
- `core/learning/flow_generator.py` — 从导航轨迹生成 Flow
- `core/learning/map_updater.py` — 地图更新

**验证标准：**
- 一次导航结束后，自动生成 Interaction Flow JSON
- 如果导航路径偏离 Golden Flow，记录偏差
- 如果发现未知节点，标记待审核

### 第五步：端到端 Demo

将所有模块连起来，用录屏数据做离线演示。

**交付物：**
- `scripts/run_demo.py` — 端到端演示脚本
- 输入：录屏文件
- 输出：导航轨迹 + 语音引导文本 + 生成的 Interaction Flow

**验证标准：**
- 给一段退款录屏，系统能自动走完整个流程
- 每一步有引导文本输出
- 结束后生成 Flow JSON

## V1.0 支持范围

- 平台：Android
- App：淘宝、京东、拼多多
- Task：退款、联系客服、查订单

## 验收标准（四件事）

1. **能否连续导航** — 用户说一次，系统一直带到结束
2. **能否自动定位** — 页面变化，无需再次询问，系统继续
3. **能否自动学习** — 一次导航，自动生成 Flow
4. **地图是否越来越完整** — 多次导航后，Golden Flow 之外的数据自动积累

## V1.0 不做

- 自动点击 / 自动操作手机
- 完整互联网地图
- 所有 App / 所有 Task
- 长期用户记忆 / 商品记忆
- AI Agent
- 语音合成（V1.0 输出文本即可）
- AI 眼镜硬件
