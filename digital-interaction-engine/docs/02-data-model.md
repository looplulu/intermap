# 数据模型

> 本文为地图引擎研究模型。1.1消费者反馈使用独立 JSONL 事件协议，
> 见 [当前数据协议](14-consumer-pilot-1.1.md)，不直接写入这里的已验证地图。

## 核心抽象

整个系统采用五层抽象：

```
Intent -> Task -> Flow -> Node -> Component
```

## 实体定义

### Intent（意图）

用户真正想完成什么。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 唯一标识 |
| name | string | 意图名称，如"退款" |
| description | string | 描述 |
| keywords | string[] | 关联关键词 |
| related_tasks | Task[] | 关联的任务 |

示例：
```json
{
  "id": "intent_refund",
  "name": "退款",
  "description": "将已购买的商品申请退款",
  "keywords": ["退款", "退货", "退钱", "不要了"],
  "related_tasks": ["task_taobao_refund", "task_jd_refund", "task_pdd_refund"]
}
```

### Task（任务）

在特定 App 中完成某件事情的具体实现。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 唯一标识 |
| app_id | string | 所属 App |
| intent_id | string | 对应的意图 |
| name | string | 任务名称 |
| flow_id | string | 关联的流程 |
| estimated_steps | int | 预计步数 |
| risks | Risk[] | 风险点列表 |

示例：
```json
{
  "id": "task_taobao_refund",
  "app_id": "app_taobao",
  "intent_id": "intent_refund",
  "name": "淘宝退款",
  "flow_id": "flow_taobao_refund",
  "estimated_steps": 5,
  "risks": [
    {"type": "irreversible", "description": "提交后不可撤销", "step": 4}
  ]
}
```

### Flow（流程）

完成某个任务的完整交互路径，由多个 Node 组成。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 唯一标识 |
| name | string | 流程名称 |
| nodes | Node[] | 节点列表（有序） |
| back_paths | BackPath[] | 回退路径 |
| branches | Branch[] | 分支条件 |

### Node（节点）

流程中的一个状态点，对应某个 App 的某个页面。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 唯一标识 |
| page_type | string | 页面语义类型 |
| app_id | string | 所属 App |
| components | Component[] | 当前页面交互组件 |
| expected_state | ExpectedState | 预期页面状态描述 |
| guidance | Guidance | 到达此节点时的引导语 |
| risks | Risk[] | 此节点的风险提示 |
| is_start | boolean | 是否为起始节点 |
| is_end | boolean | 是否为结束节点 |

示例：
```json
{
  "id": "node_taobao_order_detail",
  "page_type": "order_detail",
  "app_id": "app_taobao",
  "components": [
    {"id": "comp_refund_btn", "semantic_type": "refund_button", "required": true}
  ],
  "expected_state": {
    "description": "订单详情页，显示商品信息和操作按钮",
    "key_indicators": ["退款", "订单编号", "商品名称"]
  },
  "guidance": {
    "enter": "这是订单详情页。您可以看到商品信息和操作按钮。",
    "action": "请点击'退款'按钮开始退款流程。"
  },
  "risks": [],
  "is_start": false,
  "is_end": false
}
```

### Component（组件）

页面中的交互元素。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 唯一标识 |
| semantic_type | string | 语义类型（跨 App 统一） |
| text_patterns | string[] | 可能出现的文字模式 |
| visual_hints | VisualHint[] | 视觉特征提示 |
| action_type | string | 点击/输入/滑动等 |
| required | boolean | 是否为必需组件 |

语义类型枚举（跨 App 统一）：
- `refund_button` - 退款按钮
- `return_button` - 退货按钮
- `confirm_button` - 确认按钮
- `cancel_button` - 取消按钮
- `back_button` - 返回按钮
- `customer_service_button` - 客服按钮
- `search_box` - 搜索框
- `more_options` - 更多选项
- `order_list` - 订单列表
- `product_info` - 商品信息

### Risk（风险）

流程中的风险点。

| 字段 | 类型 | 说明 |
|------|------|------|
| type | string | 风险类型 |
| description | string | 风险描述 |
| step | int | 所在步骤 |
| severity | string | 严重级别 |

风险类型：
- `irreversible` - 不可逆操作
- `payment` - 涉及支付
- `auto_renewal` - 自动续费
- `data_loss` - 数据丢失
- `timeout` - 超时限制

### BackPath（回退路径）

从当前节点回退到之前节点的路径。

| 字段 | 类型 | 说明 |
|------|------|------|
| from_node | string | 起始节点 |
| to_node | string | 目标节点 |
| actions | Action[] | 回退操作序列 |
| guidance | string | 回退引导语 |

## 稳定层 vs 动态层

### 稳定层（地图存储）

- Intent
- Task
- Flow（节点连接关系）
- Node（语义类型）
- Component（语义类型）
- Risk
- BackPath

### 动态层（AI 实时处理）

- 页面实际布局
- 组件实际位置
- 文字实际内容
- 弹窗/广告等临时元素
- App 版本差异

## 数据库设计（MVP 阶段）

采用 SQLite + JSON 文档的混合模式：

- 关系型表：存储实体间的关联关系
- JSON 文档：存储变长、复杂的属性（如 components、guidance）

核心表：

```sql
-- 意图表
CREATE TABLE intents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    keywords TEXT, -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 任务表
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    intent_id TEXT REFERENCES intents(id),
    name TEXT NOT NULL,
    flow_id TEXT NOT NULL,
    estimated_steps INTEGER,
    risks TEXT, -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 流程表
CREATE TABLE flows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    nodes TEXT NOT NULL, -- JSON array of node IDs in order
    back_paths TEXT, -- JSON array
    branches TEXT, -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 节点表
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,
    page_type TEXT NOT NULL,
    app_id TEXT NOT NULL,
    components TEXT NOT NULL, -- JSON array
    expected_state TEXT, -- JSON
    guidance TEXT, -- JSON
    risks TEXT, -- JSON array
    is_start BOOLEAN DEFAULT 0,
    is_end BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 组件本体表（跨 App 统一语义定义）
CREATE TABLE component_ontology (
    semantic_type TEXT PRIMARY KEY,
    description TEXT,
    text_patterns TEXT, -- JSON array
    visual_hints TEXT, -- JSON array
    action_type TEXT
);

-- App 注册表
CREATE TABLE apps (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    package_name TEXT,
    platform TEXT,
    version TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
