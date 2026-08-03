import 'package:flutter_test/flutter_test.dart';
import 'package:intermap_app/models/accessibility_event.dart';
import 'package:intermap_app/services/guidance_style.dart';
import 'package:intermap_app/services/fast_navigation.dart';
import 'package:intermap_app/services/hd_map.dart';
import 'package:intermap_app/services/training_session.dart';

void main() {
  test('same page OCR drift does not announce again', () {
    final stabilizer = PageIdentityStabilizer();

    expect(stabilizer.shouldAnnounce('douyinorderdetail'), isTrue);
    expect(stabilizer.shouldAnnounce('douyinorderdetai1'), isFalse);
    expect(stabilizer.shouldAnnounce('douyinorderdetail'), isFalse);
  });

  test('new page announces on its first observation', () {
    final stabilizer = PageIdentityStabilizer();

    expect(stabilizer.shouldAnnounce('douyinhome'), isTrue);
    expect(stabilizer.shouldAnnounce('refunddetail'), isTrue);
    expect(stabilizer.shouldAnnounce('refunddetail'), isFalse);
  });

  test('training session records a page node and candidate flow', () {
    final manager = TrainingSessionManager();

    manager.start(app: 'douyin', task: 'app_exploration');
    manager.handleEvent(
      AccessibilityEventData(
        eventType: AccessibilityEventData.typeWindowContentChanged,
        packageName: 'com.ss.android.ugc.aweme',
        windowTexts: const ['推荐', '关注', '首页', '消息', '我的'],
        textSignature: '推荐|关注|首页|消息|我的',
      ),
    );

    expect(manager.eventCount, 1);
    expect(manager.nodeCount, 1);

    final flow = manager.generateCandidateFlow();
    expect(flow['app'], 'douyin');
    expect(flow['task'], 'app_exploration');
  });

  test('hybrid training preserves the exact accessibility click target', () {
    final manager = TrainingSessionManager();
    manager.start(
      app: 'douyin',
      task: 'free_exploration',
      captureMode: 'android_a11y_gui',
    );

    manager.handleEvent(
      AccessibilityEventData(
        eventType: AccessibilityEventData.typeViewClicked,
        packageName: 'com.ss.android.ugc.aweme',
        text: '我的订单',
        viewId: 'com.ss.android.ugc.aweme:id/order_entry',
        isClickable: true,
      ),
    );

    final interaction = manager.canonicalEvents.firstWhere(
      (event) => event['event_type'] == 'interaction_observed',
    );
    final payload = interaction['payload'] as Map<String, dynamic>;
    expect(payload['action_type'], 'click');
    expect(payload['target_text'], '我的订单');
    expect(
      payload['target_view_id'],
      'com.ss.android.ugc.aweme:id/order_entry',
    );
  });

  test('concise guidance removes page and operation labels', () {
    final guidance = GuidanceFormatter.fromModel(
      action: '页面名：个人主页，操作：点击右上角三个点',
      thought: '',
      style: GuidanceStyle.concise,
    );

    expect(guidance, '点击右上角三个点。');
  });

  test('detailed guidance sounds natural and includes destination', () {
    final guidance = GuidanceFormatter.fromStructured(
      page: '这是抖音首页。',
      action: '点底部右下角的“我”，进入个人中心。',
      style: GuidanceStyle.detailed,
    );

    expect(guidance, '当前是抖音首页，点底部右下角的“我”，就会进入个人中心。');
  });

  test('guidance excludes key text and amount fields', () {
    final guidance = GuidanceFormatter.fromModel(
      action: '',
      thought: '页面名：手机桌面\n操作：点击上方的抖音图标\n关键文字：抖音、小路\n金额：无',
      style: GuidanceStyle.concise,
    );

    expect(guidance, '点击上方的抖音图标。');
  });

  test('fast navigation recognizes the launcher without cloud analysis', () {
    final resolver = FastNavigationResolver(HDMap());

    final decision = resolver.resolve(
      texts: const ['18:39', '抖音', '小路'],
      app: 'douyin',
      task: 'refund',
      style: GuidanceStyle.concise,
    );

    expect(decision?.pageKey, 'android_launcher');
    expect(decision?.guidance, '点屏幕上的抖音图标。');
  });

  test('fast navigation leaves unknown screens to cloud analysis', () {
    final resolver = FastNavigationResolver(HDMap());

    final decision = resolver.resolve(
      texts: const ['一个未知页面'],
      app: 'douyin',
      task: 'refund',
      style: GuidanceStyle.concise,
    );

    expect(decision, isNull);
  });

  test('fast navigation uses verified Douyin profile correction', () {
    final resolver = FastNavigationResolver(HDMap());

    final decision = resolver.resolve(
      texts: const ['抖音号：123456', '获赞', '关注', '粉丝', '我的订单'],
      app: 'douyin',
      task: 'refund',
      style: GuidanceStyle.concise,
    );

    expect(decision?.pageKey, 'douyin_profile');
    expect(decision?.guidance, '点页面中间左侧的“我的订单”。');
  });

  test('fast navigation uses verified all-orders correction', () {
    final resolver = FastNavigationResolver(HDMap());

    final decision = resolver.resolve(
      texts: const ['全部订单', '待付款', '待发货', '待收货'],
      app: 'douyin',
      task: 'refund',
      style: GuidanceStyle.concise,
    );

    expect(decision?.pageKey, 'douyin_all_orders');
    expect(decision?.guidance, '选择你要退款的商品。');
  });

  test('fast navigation handles instant refund without cloud analysis', () {
    final resolver = FastNavigationResolver(HDMap());

    final decision = resolver.resolve(
      texts: const ['极速退款', '退款金额 49.8', '提交申请'],
      app: 'douyin',
      task: 'refund',
      style: GuidanceStyle.concise,
    );

    expect(decision?.pageKey, 'douyin_instant_refund');
    expect(decision?.guidance, '确认退款信息后，点底部的“提交申请”。');
  });
}
