import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
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
    expect(find.textContaining('抖音'), findsNothing);
    expect(find.textContaining('退款'), findsNothing);
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'same-page reminder waits four seconds after audio ends and new pages interrupt',
    (tester) async {
      var speaking = false;
      final spoken = <String>[];
      final interrupts = <bool>[];
      final speechArgs = <Map>[];
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(ConsumerSession.bridge, (call) async {
            if (call.method == 'speakNative') {
              final args = call.arguments as Map;
              speechArgs.add(args);
              if (speaking && args['interrupt'] == false) return 'busy';
              speaking = true;
              spoken.add(args['text'] as String);
              interrupts.add(args['interrupt'] as bool);
              return true;
            }
            return null;
          });
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      final session = ConsumerSession();
      session.state = TaskState.navigating;
      Map<String, dynamic> step(String page, String text) => {
        'page_key': page,
        'page_type': 'other',
        'action': 'click',
        'target_key': text,
        'step_text': text,
      };
      await session.announceGuidance(step('camera/settings', '点击左上角设置'));
      await session.announceGuidance(step('camera/settings', '点击右侧选项'));
      await session.announceGuidance(step('camera/settings', '点击下方开关'));
      expect(spoken, ['点击左上角设置']);
      speaking = false;
      session.speechCompleted();
      await session.flushGuidance();
      expect(spoken, ['点击左上角设置']);
      await tester.pump(const Duration(milliseconds: 3999));
      expect(spoken.length, 1);
      await tester.pump(const Duration(milliseconds: 1));
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pumpAndSettle();
      expect(spoken, ['点击左上角设置', '点击下方开关']);
      expect(speechArgs.last['speechRate'], closeTo(0.92, 0.001));
      expect(speechArgs.last['pitch'], 1.0);
      await session.announceGuidance(step('camera/permissions', '点击下方允许'));
      expect(spoken.last, '点击下方允许');
      expect(interrupts.last, isTrue);
      await session.announceGuidance(
        step('camera/permission-notice', '点击下方允许'),
      );
      expect(spoken.length, 3);
      await session.announceGuidance(
        step('camera/permission-notice', '点击左侧返回'),
      );
      await session.pause();
      speaking = false;
      await session.flushGuidance();
      expect(spoken.length, 3);
      session.dispose();
      debugDefaultTargetPlatformOverride = null;
    },
  );
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
  testWidgets('suspected completion pauses capture and offers a real exit', (
    tester,
  ) async {
    await tester.pumpWidget(const XiaoluApp());
    await tester.pumpAndSettle();
    final dynamic home = tester.state(find.byType(TaskHome));
    final session = home.session as ConsumerSession;
    session.state = TaskState.confirming;
    session.notifyListeners();
    await tester.pumpAndSettle();
    expect(session.state, TaskState.paused);
    expect(find.text('停止导航'), findsOneWidget);
    await tester.tap(find.text('停止导航'));
    await tester.pumpAndSettle();
    expect(session.state, TaskState.ended);
  });
  test(
    'black capture keeps projection while offering privacy recovery advice',
    () async {
      var captureStops = 0;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(ConsumerSession.bridge, (call) async {
            if (call.method == 'stopScreenCapture') captureStops++;
            return null;
          });
      final session = ConsumerSession();
      session.state = TaskState.navigating;
      await session.handleBlackScreen();
      expect(session.state, TaskState.recovering);
      expect(session.message, contains('共享仍保留'));
      expect(session.message, contains('隐私应用保护'));
      expect(session.message, contains('该项已关闭'));
      expect(captureStops, 0);
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
