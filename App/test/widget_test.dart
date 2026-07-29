import 'package:flutter_test/flutter_test.dart';
import 'package:intermap_app/models/accessibility_event.dart';
import 'package:intermap_app/services/guidance_style.dart';
import 'package:intermap_app/services/training_session.dart';

void main() {
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
}
