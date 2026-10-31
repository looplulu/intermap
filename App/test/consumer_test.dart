import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intermap_app/main.dart';
import 'package:intermap_app/services/consumer_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('flutter_tts'),
          (call) async => 1,
        );
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          ConsumerSession.bridge,
          (call) async => call.method == 'requestScreenCapture' ? false : null,
        );
  });
  testWidgets('consumer entry has text and voice without training modes', (
    tester,
  ) async {
    await tester.pumpWidget(const XiaoluApp());
    await tester.pump();
    expect(find.text('说出目标'), findsOneWidget);
    expect(find.text('开始导航'), findsOneWidget);
    expect(find.text('训练'), findsNothing);
    expect(find.text('无障碍'), findsNothing);
    expect(tester.takeException(), isNull);
  });
  test(
    'full goal is preserved and refusing projection never marks success',
    () async {
      String? goal;
      final session = ConsumerSession(
        httpClient: MockClient((r) async {
          goal = (jsonDecode(r.body) as Map)['goal'] as String?;
          return http.Response(jsonEncode({'token': 'test'}), 200);
        }),
      );
      await session.start('帮我找到刚才收藏的视频');
      expect(goal, '帮我找到刚才收藏的视频');
      expect(session.state, TaskState.paused);
      expect(session.outcome, isEmpty);
      session.dispose();
    },
  );
  test(
    'failed feedback is retained and retried before being removed',
    () async {
      var pending = '[]';
      var online = false;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(ConsumerSession.bridge, (call) async {
            if (call.method == 'loadPendingFeedback') return pending;
            if (call.method == 'savePendingFeedback') {
              pending = (call.arguments as Map)['json'] as String;
            }
            return call.method == 'requestScreenCapture' ? false : null;
          });
      final session = ConsumerSession(
        httpClient: MockClient((r) async {
          if (r.url.path.endsWith('/session')) {
            return http.Response('{"token":"test"}', 200);
          }
          return http.Response('{"ok":true}', online ? 200 : 503);
        }),
      );
      await session.start('查订单');
      await session.feedback('wrong_step');
      await Future<void>.delayed(Duration.zero);
      expect(session.pendingFeedbackCount, 1);
      expect((jsonDecode(pending) as List).length, 1);
      online = true;
      await session.retryFeedback();
      expect(session.pendingFeedbackCount, 0);
      expect(jsonDecode(pending), isEmpty);
      session.dispose();
    },
  );
  testWidgets('small screens and enlarged system text remain scrollable', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(360, 720);
    tester.view.devicePixelRatio = 1;
    tester.platformDispatcher.textScaleFactorTestValue = 1.7;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await tester.pumpWidget(const XiaoluApp());
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(find.byIcon(Icons.settings_outlined));
    await tester.pumpAndSettle();
    expect(find.text('详细语音指导'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  test(
    'stopping capture during startup cannot restart navigation after the delay',
    () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            ConsumerSession.bridge,
            (call) async => call.method == 'requestScreenCapture' ? true : null,
          );
      final session = ConsumerSession(
        httpClient: MockClient(
          (r) async => http.Response('{"token":"test"}', 200),
        ),
      );
      final starting = session.start('查订单');
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await session.pause();
      await starting;
      expect(session.state, TaskState.paused);
      session.dispose();
    },
  );
}
