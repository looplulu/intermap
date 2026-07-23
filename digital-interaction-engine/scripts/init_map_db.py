#!/usr/bin/env python3
"""
Initialize HD Interaction Map database with Taobao and JD refund flow data.
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'hd_map.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Create tables
cursor.executescript('''
CREATE TABLE IF NOT EXISTS apps (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    package_name TEXT,
    platform TEXT,
    version TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS intents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    keywords TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    intent_id TEXT,
    name TEXT NOT NULL,
    flow_id TEXT NOT NULL,
    estimated_steps INTEGER,
    risks TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS flows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    nodes TEXT NOT NULL,
    back_paths TEXT,
    branches TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    page_type TEXT NOT NULL,
    app_id TEXT NOT NULL,
    components TEXT NOT NULL,
    expected_state TEXT,
    guidance TEXT,
    risks TEXT,
    is_start BOOLEAN DEFAULT 0,
    is_end BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS component_ontology (
    semantic_type TEXT PRIMARY KEY,
    description TEXT,
    text_patterns TEXT,
    visual_hints TEXT,
    action_type TEXT
);
''')

# Insert App
cursor.execute('''
INSERT OR REPLACE INTO apps (id, name, package_name, platform, version)
VALUES (?, ?, ?, ?, ?)
''', ('app_taobao', '淘宝', 'com.taobao.taobao', 'iOS/Android', 'v15.x'))

# Insert Intent
cursor.execute('''
INSERT OR REPLACE INTO intents (id, name, description, keywords)
VALUES (?, ?, ?, ?)
''', ('intent_refund', '退款/退货', '将已购买的商品申请退款或退货', 
      json.dumps(['退款', '退货', '退钱', '售后', '不要了', '买错了'])))

# Insert Component Ontology
cursor.execute('''
INSERT OR REPLACE INTO component_ontology (semantic_type, description, text_patterns, visual_hints, action_type)
VALUES (?, ?, ?, ?, ?)
''', ('aftersales_button', '售后/退款入口按钮', 
      json.dumps(['退款/售后', '申请售后', '售后']), None, 'click'))

cursor.execute('''
INSERT OR REPLACE INTO component_ontology (semantic_type, description, text_patterns, visual_hints, action_type)
VALUES (?, ?, ?, ?, ?)
''', ('order_detail_button', '订单详情入口', 
      json.dumps(['查看物流', '订单详情', '申请售后']), None, 'click'))

cursor.execute('''
INSERT OR REPLACE INTO component_ontology (semantic_type, description, text_patterns, visual_hints, action_type)
VALUES (?, ?, ?, ?, ?)
''', ('next_button', '下一步按钮', 
      json.dumps(['下一步', '继续']), None, 'click'))

cursor.execute('''
INSERT OR REPLACE INTO component_ontology (semantic_type, description, text_patterns, visual_hints, action_type)
VALUES (?, ?, ?, ?, ?)
''', ('back_button', '返回/上一步按钮', 
      json.dumps(['上一步', '返回', '取消']), None, 'click'))

cursor.execute('''
INSERT OR REPLACE INTO component_ontology (semantic_type, description, text_patterns, visual_hints, action_type)
VALUES (?, ?, ?, ?, ?)
''', ('radio_option', '单选选项', 
      json.dumps([]), None, 'click'))

# Insert Nodes for Taobao Refund Flow
# Corrected flow based on actual recording:
# home -> mine_center -> order_list -> order_detail -> aftersales_type -> aftersales_reason -> submit -> result
nodes_data = [
    {
        'id': 'node_taobao_home',
        'page_type': 'home',
        'app_id': 'app_taobao',
        'components': json.dumps([
            {'semantic_type': 'tab_mine', 'required': True}
        ]),
        'expected_state': json.dumps({
            'description': '淘宝首页，底部导航栏有首页、视频、消息、购物车、我的淘宝',
            'key_indicators': ['首页', '推荐', '搜索', '我的淘宝']
        }),
        'guidance': json.dumps({
            'enter': '这是淘宝首页。',
            'action': '请点击底部“我的淘宝”进入个人中心。'
        }),
        'risks': '[]',
        'is_start': 1,
        'is_end': 0
    },
    {
        'id': 'node_taobao_mine',
        'page_type': 'mine_center',
        'app_id': 'app_taobao',
        'components': json.dumps([
            {'semantic_type': 'order_entry', 'required': True}
        ]),
        'expected_state': json.dumps({
            'description': '我的淘宝个人中心页面，包含“我的订单”模块，下方有待付款/待发货/待收货/待评价/退款售后五个快捷入口',
            'key_indicators': ['我的订单', '全部', '待付款', '待发货', '待收货', '待评价', '退款/售后']
        }),
        'guidance': json.dumps({
            'enter': '这是您的个人中心。这里可以看到订单相关信息。',
            'action': '请点击“我的订单”旁边的“全部”按钮，进入订单列表。'
        }),
        'risks': '[]',
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_taobao_order_list',
        'page_type': 'order_list',
        'app_id': 'app_taobao',
        'components': json.dumps([
            {'semantic_type': 'order_status_filter', 'required': True},
            {'semantic_type': 'order_card', 'required': True}
        ]),
        'expected_state': json.dumps({
            'description': '订单列表页，顶部有全部/待付款/待发货/待收货/退款售后筛选标签，下方显示订单卡片列表。可以从“全部”或“待收货”中找到需要退款的订单。',
            'key_indicators': ['全部订单', '购物', '搜索订单', '全部', '待付款', '待发货', '待收货', '退款/售后', '交易成功']
        }),
        'guidance': json.dumps({
            'enter': '这是订单列表。您可以从“全部”或“待收货”里找到要退款的订单。',
            'action': '请找到需要退款的商品订单，点击进入订单详情。'
        }),
        'risks': '[]',
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_taobao_order_detail',
        'page_type': 'order_detail',
        'app_id': 'app_taobao',
        'components': json.dumps([
            {'semantic_type': 'product_apply_aftersales', 'required': True}
        ]),
        'expected_state': json.dumps({
            'description': '订单详情页（交易成功），显示物流信息、商品列表、价格信息、服务保障（退货包运费/买贵必赔/假一赔十）。每个商品下方有“申请售后”按钮。',
            'key_indicators': ['交易成功', '已签收', '申请售后', '查看物流', '实付款', '退货包运费', '7天无理由退换', '假一赔十']
        }),
        'guidance': json.dumps({
            'enter': '这是订单详情页。这里显示了商品信息、物流状态和售后服务入口。',
            'action': '请点击要退款商品下方的“申请售后”按钮。'
        }),
        'risks': json.dumps([
            {'type': 'time_limit', 'description': '注意“7天无理由退换”是否已过期，如过期需与商家协商', 'severity': 'high'}
        ]),
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_taobao_aftersales_type',
        'page_type': 'aftersales_type',
        'app_id': 'app_taobao',
        'components': json.dumps([
            {'semantic_type': 'radio_option', 'required': True},
            {'semantic_type': 'next_button', 'required': True},
            {'semantic_type': 'close_button', 'required': False}
        ]),
        'expected_state': json.dumps({
            'description': '选择售后类型弹窗（底部弹出）。显示商品信息、7天无理由状态、88VIP运费权益。三个选项：退货/退款（推荐）、换货、补寄。',
            'key_indicators': ['选择售后类型', '退货/退款', '换货', '补寄', '下一步', '建议先与商家协商一致']
        }),
        'guidance': json.dumps({
            'enter': '请选择售后类型。系统推荐“退货/退款”。注意查看7天无理由退换是否过期。',
            'action': '请选择“退货/退款”，然后点击“下一步”。如果7天已过期，建议先与商家协商。'
        }),
        'risks': json.dumps([
            {'type': 'time_limit', 'description': '如果“7天无理由退换·已过期”，商家有权拒绝，需先协商', 'severity': 'high'},
            {'type': 'info', 'description': '88VIP享退货包运费权益', 'severity': 'low'}
        ]),
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_taobao_aftersales_reason',
        'page_type': 'aftersales_reason',
        'app_id': 'app_taobao',
        'components': json.dumps([
            {'semantic_type': 'tab_switch', 'required': True},
            {'semantic_type': 'radio_option', 'required': True},
            {'semantic_type': 'next_button', 'required': True},
            {'semantic_type': 'back_button', 'required': False}
        ]),
        'expected_state': json.dumps({
            'description': '选择售后原因弹窗（底部弹出）。顶部有“退款”和“退货退款”两个Tab。退货退款模式有11个原因选项：买贵了/少用优惠、协商一致退款、颜色款式不符、材质不符、做工粗糙、质量问题、少件、破损污渍、假冒品牌、发票问题、发错货。',
            'key_indicators': ['选择售后原因', '退款', '退货退款', '买贵了', '协商一致退款', '质量问题', '颜色', '下一步', '上一步']
        }),
        'guidance': json.dumps({
            'enter': '请选择退款原因。顶部可以在“退款”和“退货退款”之间切换。',
            'action': '请选择一个最符合实际情况的原因，然后点击“下一步”。如果选错了，可以点击“上一步”返回。'
        }),
        'risks': json.dumps([
            {'type': 'data_loss', 'description': '原因选择可能影响退款成功率，建议如实选择', 'severity': 'medium'}
        ]),
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_taobao_refund_submit',
        'page_type': 'refund_submit',
        'app_id': 'app_taobao',
        'components': json.dumps([
            {'semantic_type': 'confirm_button', 'required': True},
            {'semantic_type': 'back_button', 'required': False}
        ]),
        'expected_state': json.dumps({
            'description': '退款申请提交确认页',
            'key_indicators': ['提交', '确认', '退款金额', '退款说明']
        }),
        'guidance': json.dumps({
            'enter': '请确认退款信息是否正确。',
            'action': '确认无误后，请点击“提交”按钮完成退款申请。'
        }),
        'risks': json.dumps([
            {'type': 'irreversible', 'description': '提交后不可撤销，需谨慎确认', 'severity': 'high'}
        ]),
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_taobao_refund_result',
        'page_type': 'refund_result',
        'app_id': 'app_taobao',
        'components': json.dumps([]),
        'expected_state': json.dumps({
            'description': '退款申请结果页',
            'key_indicators': ['申请成功', '等待商家处理', '退款进度']
        }),
        'guidance': json.dumps({
            'enter': '退款申请已提交成功。',
            'action': '商家会在规定时间内处理您的申请，您可以在退款/售后中查看进度。'
        }),
        'risks': '[]',
        'is_start': 0,
        'is_end': 1
    }
]

for node in nodes_data:
    cursor.execute('''
    INSERT OR REPLACE INTO nodes (id, page_type, app_id, components, expected_state, guidance, risks, is_start, is_end)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (node['id'], node['page_type'], node['app_id'], node['components'], 
          node['expected_state'], node['guidance'], node['risks'], node['is_start'], node['is_end']))

# Insert Flow
flow_nodes = json.dumps([
    'node_taobao_home',
    'node_taobao_mine', 
    'node_taobao_order_list',
    'node_taobao_order_detail',
    'node_taobao_aftersales_type',
    'node_taobao_aftersales_reason',
    'node_taobao_refund_submit',
    'node_taobao_refund_result'
])

back_paths = json.dumps([
    {
        'from_node': 'node_taobao_aftersales_type',
        'to_node': 'node_taobao_order_detail',
        'actions': ['点击右上角关闭按钮X'],
        'guidance': '如需返回订单详情，请点击右上角的X关闭按钮。'
    },
    {
        'from_node': 'node_taobao_aftersales_reason',
        'to_node': 'node_taobao_aftersales_type',
        'actions': ['点击上一步'],
        'guidance': '如需修改售后类型，请点击"上一步"。'
    }
])

cursor.execute('''
INSERT OR REPLACE INTO flows (id, name, nodes, back_paths, branches)
VALUES (?, ?, ?, ?, ?)
''', ('flow_taobao_refund', '淘宝退款/退货流程', flow_nodes, back_paths, '[]'))

# Insert Task
cursor.execute('''
INSERT OR REPLACE INTO tasks (id, app_id, intent_id, name, flow_id, estimated_steps, risks)
VALUES (?, ?, ?, ?, ?, ?, ?)
''', ('task_taobao_refund', 'app_taobao', 'intent_refund', '淘宝退款/退货', 
      'flow_taobao_refund', 7, json.dumps([
          {'type': 'time_limit', 'description': '注意7天无理由退换期限', 'step': 2},
          {'type': 'irreversible', 'description': '提交后不可撤销', 'step': 5}
      ])))

# ============================================================
# JD (京东) Refund Flow
# Flow: home -> mine -> order_list -> order_detail -> aftersales_hub -> aftersales_type -> aftersales_reason -> submit -> result
# ============================================================

# Insert JD App
cursor.execute('''
INSERT OR REPLACE INTO apps (id, name, package_name, platform, version)
VALUES (?, ?, ?, ?, ?)
''', ('app_jd', '京东', 'com.jingdong.app.mall', 'iOS/Android', 'v13.x'))

# JD Component Ontology
cursor.execute('''
INSERT OR REPLACE INTO component_ontology (semantic_type, description, text_patterns, visual_hints, action_type)
VALUES (?, ?, ?, ?, ?)
''', ('price_protection', '价格保护选项',
      json.dumps(['价格保护']), None, 'click'))

cursor.execute('''
INSERT OR REPLACE INTO component_ontology (semantic_type, description, text_patterns, visual_hints, action_type)
VALUES (?, ?, ?, ?, ?)
''', ('aftersales_hub_entry', '退换/售后入口页',
      json.dumps(['退换/售后', '退款/售后']), None, 'click'))

# JD Nodes
jd_nodes_data = [
    {
        'id': 'node_jd_home',
        'page_type': 'home',
        'app_id': 'app_jd',
        'components': json.dumps([
            {'semantic_type': 'tab_mine', 'required': True}
        ]),
        'expected_state': json.dumps({
            'description': '京东首页，底部导航栏有首页、待领取、消息、购物车、我的',
            'key_indicators': ['首页', '推荐', '搜索', '我的']
        }),
        'guidance': json.dumps({
            'enter': '这是京东首页。',
            'action': '请点击底部"我的"进入个人中心。'
        }),
        'risks': '[]',
        'is_start': 1,
        'is_end': 0
    },
    {
        'id': 'node_jd_mine',
        'page_type': 'mine_center',
        'app_id': 'app_jd',
        'components': json.dumps([
            {'semantic_type': 'order_entry', 'required': True}
        ]),
        'expected_state': json.dumps({
            'description': '京东个人中心页面，包含我的订单入口',
            'key_indicators': ['我的订单', '全部', '待付款', '待收货']
        }),
        'guidance': json.dumps({
            'enter': '这是您的京东个人中心。',
            'action': '请点击"我的订单"旁边的"全部"按钮，进入订单列表。'
        }),
        'risks': '[]',
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_jd_order_list',
        'page_type': 'order_list',
        'app_id': 'app_jd',
        'components': json.dumps([
            {'semantic_type': 'order_status_filter', 'required': True},
            {'semantic_type': 'order_card', 'required': True}
        ]),
        'expected_state': json.dumps({
            'description': '京东订单列表页，有两级筛选：第一级按业务线（全部/购物/秒送/外卖/服务/家政），第二级按状态（待付款/待收货/待使用/已完成）。下方显示订单卡片列表。',
            'key_indicators': ['全部订单', '购物', '全部', '待付款', '待收货', '已完成', '搜索我的订单', '退款/售后']
        }),
        'guidance': json.dumps({
            'enter': '这是京东订单列表。您可以从"全部"或"待收货"里找到要退款的订单。',
            'action': '请找到需要退款的商品订单，点击进入订单详情。'
        }),
        'risks': '[]',
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_jd_order_detail',
        'page_type': 'order_detail',
        'app_id': 'app_jd',
        'components': json.dumps([
            {'semantic_type': 'order_action_button', 'required': True}
        ]),
        'expected_state': json.dumps({
            'description': '京东订单详情页，显示商品信息、物流状态、收货人信息、商家信息。底部有操作按钮（退款/售后、确认收货、再次购买等）。',
            'key_indicators': ['订单详情', '已完成', '已签收', '退款/售后', '确认收货', '联系客服', '不支持7天无理由退货']
        }),
        'guidance': json.dumps({
            'enter': '这是京东订单详情页。这里显示了商品信息和订单状态。',
            'action': '请点击底部的"退款/售后"按钮。'
        }),
        'risks': json.dumps([
            {'type': 'time_limit', 'description': '注意是否"不支持7天无理由退货"', 'severity': 'high'}
        ]),
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_jd_aftersales_hub',
        'page_type': 'aftersales_hub',
        'app_id': 'app_jd',
        'components': json.dumps([
            {'semantic_type': 'aftersales_tab_filter', 'required': True},
            {'semantic_type': 'aftersales_product_card', 'required': True}
        ]),
        'expected_state': json.dumps({
            'description': '京东退换/售后中间页（淘宝没有此页面）。顶部有四个Tab：售后申请、处理中、待评价、申请记录。下方显示可申请售后的商品列表，每个商品有"退款/售后"按钮。支持按订单号搜索。',
            'key_indicators': ['退换/售后', '售后申请', '处理中', '待评价', '申请记录', '退款/售后']
        }),
        'guidance': json.dumps({
            'enter': '这是京东的售后服务中心。这里列出了您可以申请售后的商品。',
            'action': '请点击要退款商品旁边的"退款/售后"按钮。'
        }),
        'risks': '[]',
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_jd_aftersales_type',
        'page_type': 'aftersales_type',
        'app_id': 'app_jd',
        'components': json.dumps([
            {'semantic_type': 'radio_option', 'required': True},
            {'semantic_type': 'next_button', 'required': True},
            {'semantic_type': 'close_button', 'required': False}
        ]),
        'expected_state': json.dumps({
            'description': '选择售后类型页面。页面标题"选择退款售后商品"。选项：退货、换货、价格保护（京东特色）。',
            'key_indicators': ['选择退款售后商品', '请选择售后类型', '退货', '换货', '价格保护']
        }),
        'guidance': json.dumps({
            'enter': '请选择售后类型。',
            'action': '通常选择"退货"。如果商品降价了，可以选择"价格保护"退差价。'
        }),
        'risks': json.dumps([
            {'type': 'info', 'description': '价格保护是京东特色功能，如果商品降价可退差价', 'severity': 'low'}
        ]),
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_jd_aftersales_reason',
        'page_type': 'aftersales_reason',
        'app_id': 'app_jd',
        'components': json.dumps([
            {'semantic_type': 'radio_option', 'required': True},
            {'semantic_type': 'confirm_button', 'required': True},
            {'semantic_type': 'close_button', 'required': False}
        ]),
        'expected_state': json.dumps({
            'description': '选择退款原因弹窗（底部弹出）。11个选项：买多/买错/不想要、商品质量问题、商品与页面描述不符、效期问题、商品/包装破损、包装简陋、发错货、少件、价格问题、赠品问题、未收到货。',
            'key_indicators': ['申请原因', '买多/买错/不想要', '商品质量问题', '商品与页面描述不符', '效期问题', '商品/包装破损', '确认']
        }),
        'guidance': json.dumps({
            'enter': '请选择退款原因。',
            'action': '请选择一个最符合实际情况的原因，然后点击"确认"。'
        }),
        'risks': json.dumps([
            {'type': 'data_loss', 'description': '原因选择可能影响退款成功率', 'severity': 'medium'}
        ]),
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_jd_refund_submit',
        'page_type': 'refund_submit',
        'app_id': 'app_jd',
        'components': json.dumps([
            {'semantic_type': 'confirm_button', 'required': True},
            {'semantic_type': 'back_button', 'required': False}
        ]),
        'expected_state': json.dumps({
            'description': '退款申请提交确认页',
            'key_indicators': ['提交', '确认', '退款金额', '退款说明']
        }),
        'guidance': json.dumps({
            'enter': '请确认退款信息是否正确。',
            'action': '确认无误后，请点击"提交"按钮完成退款申请。'
        }),
        'risks': json.dumps([
            {'type': 'irreversible', 'description': '提交后不可撤销', 'severity': 'high'}
        ]),
        'is_start': 0,
        'is_end': 0
    },
    {
        'id': 'node_jd_refund_result',
        'page_type': 'refund_result',
        'app_id': 'app_jd',
        'components': json.dumps([]),
        'expected_state': json.dumps({
            'description': '退款申请结果页',
            'key_indicators': ['申请成功', '等待商家处理', '退款进度']
        }),
        'guidance': json.dumps({
            'enter': '退款申请已提交成功。',
            'action': '商家会在规定时间内处理您的申请，您可以在退换/售后中查看进度。'
        }),
        'risks': '[]',
        'is_start': 0,
        'is_end': 1
    }
]

for node in jd_nodes_data:
    cursor.execute('''
    INSERT OR REPLACE INTO nodes (id, page_type, app_id, components, expected_state, guidance, risks, is_start, is_end)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (node['id'], node['page_type'], node['app_id'], node['components'],
          node['expected_state'], node['guidance'], node['risks'], node['is_start'], node['is_end']))

# JD Flow
jd_flow_nodes = json.dumps([
    'node_jd_home',
    'node_jd_mine',
    'node_jd_order_list',
    'node_jd_order_detail',
    'node_jd_aftersales_hub',
    'node_jd_aftersales_type',
    'node_jd_aftersales_reason',
    'node_jd_refund_submit',
    'node_jd_refund_result'
])

jd_back_paths = json.dumps([
    {
        'from_node': 'node_jd_aftersales_hub',
        'to_node': 'node_jd_order_detail',
        'actions': ['点击返回箭头'],
        'guidance': '如需返回订单详情，请点击左上角返回箭头。'
    },
    {
        'from_node': 'node_jd_aftersales_type',
        'to_node': 'node_jd_aftersales_hub',
        'actions': ['点击返回箭头或关闭按钮'],
        'guidance': '如需返回售后中心，请点击返回或关闭。'
    },
    {
        'from_node': 'node_jd_aftersales_reason',
        'to_node': 'node_jd_aftersales_type',
        'actions': ['点击关闭按钮X'],
        'guidance': '如需修改售后类型，请点击X关闭弹窗。'
    }
])

cursor.execute('''
INSERT OR REPLACE INTO flows (id, name, nodes, back_paths, branches)
VALUES (?, ?, ?, ?, ?)
''', ('flow_jd_refund', '京东退款/退货流程', jd_flow_nodes, jd_back_paths, '[]'))

# JD Task
cursor.execute('''
INSERT OR REPLACE INTO tasks (id, app_id, intent_id, name, flow_id, estimated_steps, risks)
VALUES (?, ?, ?, ?, ?, ?, ?)
''', ('task_jd_refund', 'app_jd', 'intent_refund', '京东退款/退货',
      'flow_jd_refund', 8, json.dumps([
          {'type': 'time_limit', 'description': '部分商品不支持7天无理由退货', 'step': 3},
          {'type': 'irreversible', 'description': '提交后不可撤销', 'step': 6}
      ])))

conn.commit()
conn.close()

print(f"Database initialized at: {DB_PATH}")
print("Tables created: apps, intents, tasks, flows, nodes, component_ontology")
print("Data inserted: 2 apps, 1 intent, 2 tasks, 2 flows, 16 nodes, 7 component types")
