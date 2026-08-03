import 'guidance_style.dart';
import 'hd_map.dart';

class FastNavigationDecision {
  final String pageKey;
  final String pageName;
  final String guidance;
  final List<String> risks;
  final double confidence;

  const FastNavigationDecision({
    required this.pageKey,
    required this.pageName,
    required this.guidance,
    required this.risks,
    required this.confidence,
  });
}

class FastNavigationResolver {
  final HDMap hdMap;

  const FastNavigationResolver(this.hdMap);

  FastNavigationDecision? resolve({
    required List<String> texts,
    required String app,
    required String task,
    required GuidanceStyle style,
  }) {
    final cleanTexts = texts
        .map((text) => text.trim())
        .where((text) => text.isNotEmpty)
        .toList();
    final fullText = cleanTexts.join(' ');

    FastNavigationDecision decision({
      required String pageKey,
      required String pageName,
      required String page,
      required String action,
      double confidence = 0.88,
    }) {
      return FastNavigationDecision(
        pageKey: pageKey,
        pageName: pageName,
        guidance: GuidanceFormatter.fromStructured(
          page: page,
          action: action,
          style: style,
        ),
        risks: const [],
        confidence: confidence,
      );
    }

    if (!fullText.contains('推荐') &&
        !fullText.contains('关注') &&
        fullText.contains('抖音')) {
      return const FastNavigationDecision(
        pageKey: 'android_launcher',
        pageName: '手机桌面',
        guidance: '点屏幕上的抖音图标。',
        risks: [],
        confidence: 0.9,
      );
    }

    if (fullText.contains('抽奖') &&
        (fullText.contains('立即抽奖') || fullText.contains('抽奖机会'))) {
      return decision(
        pageKey: 'douyin_lottery_popup',
        pageName: '抽奖弹窗',
        page: '当前是抽奖弹窗。',
        action: '点弹窗右上角的关闭按钮。',
      );
    }

    if (fullText.contains('退款原因') &&
        (fullText.contains('请选择') || fullText.contains('选择原因'))) {
      return decision(
        pageKey: 'douyin_refund_reason',
        pageName: '退款原因选择页',
        page: '当前是退款原因选择页。',
        action: '选择符合实际情况的退款原因。',
      );
    }

    if (fullText.contains('申请退款') &&
        (fullText.contains('订单详情') || fullText.contains('待发货'))) {
      return decision(
        pageKey: 'douyin_order_detail',
        pageName: '待发货订单详情',
        page: '当前是待发货订单详情页。',
        action: '点商品右侧的“申请退款”。',
      );
    }

    if (fullText.contains('全部订单') &&
        (fullText.contains('待付款') ||
            fullText.contains('待发货') ||
            fullText.contains('待收货'))) {
      return decision(
        pageKey: 'douyin_all_orders',
        pageName: '全部订单',
        page: '当前是全部订单页。',
        action: '选择你要退款的商品。',
      );
    }

    if (fullText.contains('抖音商城') && fullText.contains('我的订单')) {
      return decision(
        pageKey: 'douyin_mall_profile',
        pageName: '抖音商城个人页',
        page: '当前是抖音商城个人页。',
        action: '点左上角的“我的订单”。',
      );
    }

    if (fullText.contains('抖音号') &&
        (fullText.contains('获赞') || fullText.contains('粉丝'))) {
      return decision(
        pageKey: 'douyin_profile',
        pageName: '抖音个人主页',
        page: '当前是抖音个人主页。',
        action: '点页面中间左侧的“我的订单”。',
      );
    }

    if (fullText.contains('推荐') &&
        fullText.contains('关注') &&
        (fullText.contains('首页') || fullText.contains('消息'))) {
      return decision(
        pageKey: 'douyin_home',
        pageName: '抖音首页',
        page: '当前是抖音首页。',
        action: '点底部右下角的“我”。',
      );
    }

    final match = hdMap.matchNode(
      texts: cleanTexts,
      viewIds: const [],
      activity: '',
      app: app,
      task: task,
    );
    final node = match.node;
    if (node == null || match.nodeId == null || match.confidence < 0.5) {
      return null;
    }

    final guidance = GuidanceFormatter.fromStructured(
      page: node.guidance.enter,
      action: node.guidance.action,
      style: style,
    );
    final risks = node.risks
        .map((risk) => risk.description ?? '')
        .where((risk) => risk.isNotEmpty)
        .toList();
    return FastNavigationDecision(
      pageKey: 'map_${match.nodeId}',
      pageName: node.pageType,
      guidance: guidance,
      risks: risks,
      confidence: match.confidence,
    );
  }
}
