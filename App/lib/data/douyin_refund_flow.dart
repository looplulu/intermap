/// 抖音退货/退款 Golden Flow
/// 后续将通过训练系统从真实操作中生成，这是初始版本
const douyinRefundFlow = {
  'flow_id': 'douyin_refund',
  'app': 'douyin',
  'task': 'refund',
  'description': '抖音退款/退货主流程',
  'nodes': [
    {
      'node_id': 'android_launcher',
      'page_type': 'launcher',
      'key_indicators': ['抖音', '小路'],
      'guidance': {
        'enter': '这是手机桌面。',
        'action': '找到黑色方形里有彩色音符、下方写着“抖音”的应用图标，点一下。',
      },
      'risks': [],
      'is_start': true,
      'is_end': false,
    },
    {
      'node_id': 'douyin_home',
      'page_type': 'home',
      'key_indicators': ['推荐', '关注', '我的', '首页', '消息'],
      'guidance': {'enter': '这是抖音首页。', 'action': '点底部右下角的"我"，进入个人中心。'},
      'risks': [],
      'is_start': false,
      'is_end': false,
    },
    {
      'node_id': 'douyin_mine',
      'page_type': 'profile',
      'key_indicators': ['我的', '抖音号', '获赞', '关注', '粉丝'],
      'guidance': {
        'enter': '这是你的个人中心。',
        'action': '点页面中间偏左、带购物车图案且下方写着“我的订单”的入口。',
      },
      'risks': [
        {'description': '不要误点"设置"', 'type': 'wrong_button'},
      ],
      'is_start': false,
      'is_end': false,
    },
    {
      'node_id': 'douyin_order_center',
      'page_type': 'order_center',
      'key_indicators': ['我的订单', '全部订单', '退款/售后'],
      'guidance': {'enter': '这是订单入口页。', 'action': '点页面里的“全部订单”，不要点“退款/售后”。'},
      'risks': [
        {'description': '退款要先从全部订单选择目标订单', 'type': 'wrong_button'},
      ],
      'is_start': false,
      'is_end': false,
    },
    {
      'node_id': 'douyin_orders',
      'page_type': 'order_list',
      'key_indicators': ['订单', '全部', '待付款', '待发货', '待收货', '退款'],
      'guidance': {
        'enter': '这是全部订单列表。',
        'action': '你自己找到想退款的那笔订单，再点订单里的商品进入详情。',
      },
      'risks': [],
      'is_start': false,
      'is_end': false,
    },
    {
      'node_id': 'douyin_order_detail',
      'page_type': 'order_detail',
      'key_indicators': ['订单详情', '退款', '联系商家', '确认收货'],
      'guidance': {'enter': '这是订单详情页。', 'action': '点"申请退款"按钮。'},
      'risks': [
        {'description': '不要点"确认收货"，点了就不能退款了', 'type': 'danger'},
      ],
      'is_start': false,
      'is_end': false,
    },
    {
      'node_id': 'douyin_refund_form',
      'page_type': 'refund_form',
      'key_indicators': ['申请退款', '退款原因', '退款说明', '提交'],
      'guidance': {'enter': '这是退款申请页。', 'action': '选择退款原因，然后点"提交"。'},
      'risks': [],
      'is_start': false,
      'is_end': false,
    },
    {
      'node_id': 'douyin_refund_result',
      'page_type': 'refund_result',
      'key_indicators': ['退款成功', '退款中', '预计', '个工作日'],
      'guidance': {
        'enter': '退款已提交。',
        'action': '退款申请已提交，请等待商家处理。通常1-3个工作日会有结果。',
      },
      'risks': [],
      'is_start': false,
      'is_end': true,
    },
  ],
  'edges': [
    {'from': 'android_launcher', 'to': 'douyin_home'},
    {'from': 'douyin_home', 'to': 'douyin_mine'},
    {'from': 'douyin_mine', 'to': 'douyin_order_center'},
    {'from': 'douyin_order_center', 'to': 'douyin_orders'},
    {'from': 'douyin_orders', 'to': 'douyin_order_detail'},
    {'from': 'douyin_order_detail', 'to': 'douyin_refund_form'},
    {'from': 'douyin_refund_form', 'to': 'douyin_refund_result'},
  ],
};
