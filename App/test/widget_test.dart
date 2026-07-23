import 'package:flutter_test/flutter_test.dart';
import 'package:intermap_app/models/accessibility_event.dart';
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
}
