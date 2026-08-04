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
        'action': '在手机桌面，点击“抖音”，它是黑色方形里有彩色音符的应用图标。',
      },
      'risks': [],
      'is_start': true,
      'is_end': false,
    },
    {
      'node_id': 'douyin_home',
      'page_type': 'home',
      'key_indicators': ['推荐', '关注', '我的', '首页', '消息'],
      'guidance': {'enter': '这是抖音首页。', 'action': '在页面底部右下角，点击“我”。'},
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
        'action': '在页面中间偏左，点击当前显示的订单入口，它是购物车图标。',
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
      'guidance': {
        'enter': '这是商城订单入口页。',
        'action': '在页面左上角，点击第二个“我的订单”，不要点击“退款/售后”。',
      },
      'risks': [
        {'description': '“退款/售后”只用于查看已申请的售后', 'type': 'wrong_button'},
      ],
      'is_start': false,
      'is_end': false,
    },
    {
      'node_id': 'douyin_orders',
      'page_type': 'order_list',
      'key_indicators': ['订单', '全部', '待付款', '待发货', '待收货', '退款'],
      'guidance': {'enter': '这是全部订单列表。', 'action': '在订单列表中，点击你想退货的商品。'},
      'risks': [],
      'is_start': false,
      'is_end': false,
    },
    {
      'node_id': 'douyin_order_detail',
      'page_type': 'order_detail',
      'key_indicators': ['订单详情', '退款', '联系商家', '确认收货'],
      'guidance': {'enter': '这是订单详情页。', 'action': '在商品右侧，点击“申请退款”。'},
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
      'guidance': {'enter': '这是退款申请页。', 'action': '在退款原因栏选择原因，然后在页面底部点击“提交”。'},
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
