import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'screen_capture_service.dart';
import 'tts_service.dart';

enum TaskState {
  idle,
  authorizing,
  navigating,
  waiting,
  paused,
  confirming,
  ended,
}

class ConsumerSession extends ChangeNotifier {
  static const bridge = MethodChannel('com.intermap/app');
  final capture = ScreenCaptureManager();
  final tts = TTSService();
  final http.Client client;
  ConsumerSession({http.Client? httpClient})
    : client = httpClient ?? http.Client() {
    tts.onComplete = () => unawaited(flushGuidance());
    _feedbackTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      unawaited(retryFeedback().catchError((_) {}));
    });
  }
  late final Timer _feedbackTimer;
  final detector = FrameChangeDetector(minInterval: Duration.zero);
  TaskState state = TaskState.idle;
  String goal = '', guidance = '', message = '', outcome = '';
  bool consent = false, detailed = false;
  int pendingFeedbackCount = 0;
  String _token = '';
  int _epoch = 0;
  int _requestId = 0;
  bool _busy = false;
  String? _pending;
  String _spokenTarget = '';
  String _spokenPage = '';
  String _spokenText = '';
  bool _flushingGuidance = false;
  Map<String, dynamic>? _pendingGuidance;
  int? _stepId;
  Future<void> _feedbackWork = Future<void>.value();
  Future<void>? _outboxReady;
  final List<Map<String, dynamic>> _outbox = [];
  bool _flushing = false, _disposed = false;

  Future<Map<String, dynamic>> request(
    String route,
    Map<String, dynamic> body, {
    String? token,
  }) async {
    final response = await client
        .post(
          Uri.parse('https://loop-lulu.com/intermap/api/consumer/$route'),
          headers: {
            'Content-Type': 'application/json',
            if ((token ?? _token).isNotEmpty)
              'Authorization': 'Bearer ${token ?? _token}',
          },
          body: jsonEncode(body),
        )
        .timeout(Duration(seconds: route == 'feedback' ? 4 : 22));
    if (response.statusCode != 200) {
      throw Exception(
        response.statusCode == 429 ? '本次试用额度已用完，请稍后再试' : '暂时无法连接导航服务，请暂停后重试',
      );
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<void> start(String text) async {
    if (text.trim().isEmpty || state == TaskState.authorizing) return;
    if (_token.isNotEmpty) await finish(false);
    ++_requestId;
    _busy = false;
    _pending = null;
    await _loadOutbox();
    unawaited(retryFeedback());
    final epoch = ++_epoch;
    goal = text.trim();
    guidance = '';
    outcome = '';
    _spokenTarget = '';
    _spokenPage = '';
    _spokenText = '';
    _pendingGuidance = null;
    _stepId = null;
    state = TaskState.authorizing;
    message = '正在准备本次导航';
    notifyListeners();
    try {
      final environment = await bridge.invokeMapMethod<String, dynamic>(
        'getEnvironment',
      );
      final data = await request('session', {
        'goal': goal,
        'consent': consent,
        'environment': environment,
      });
      if (epoch != _epoch) return;
      _token = data['token'] as String;
      if (!await capture.requestPermission()) {
        state = TaskState.paused;
        message = '没有取得共享权限，可以再次开始';
        notifyListeners();
        return;
      }
      if (epoch != _epoch) {
        await capture.stop();
        return;
      }
      await bridge.invokeMethod('moveToBackground');
      await Future<void>.delayed(const Duration(milliseconds: 450));
      if (epoch != _epoch) return;
      detector.reset();
      state = TaskState.navigating;
      message = '正在看当前画面';
      notifyListeners();
      capture.startListening(_frame);
    } catch (e) {
      state = TaskState.paused;
      message = '$e';
      notifyListeners();
    }
  }

  void _frame(String frame) {
    if (state != TaskState.navigating && state != TaskState.waiting) return;
    if (!detector.shouldAnalyze(frame)) return;
    if (_busy) {
      _pending = frame;
      return;
    }
    unawaited(_analyze(frame));
  }

  Future<void> _analyze(String frame) async {
    final epoch = _epoch;
    final requestId = ++_requestId;
    _busy = true;
    try {
      final data = await request('frame', {
        'image': 'data:image/jpeg;base64,$frame',
      });
      if (epoch != _epoch ||
          state == TaskState.paused ||
          state == TaskState.ended) {
        return;
      }
      final next = data['step_text'] as String;
      _stepId = data['step_id'] as int?;
      final action = data['action'];
      if (action == 'private') {
        guidance = next;
        await pause();
        message = '请自行处理敏感操作，完成后再继续';
        await tts.speak(message);
        await bridge.invokeMethod('updateCompanion', {'text': message});
        notifyListeners();
        return;
      }
      state = action == 'confirm_result'
          ? TaskState.confirming
          : TaskState.navigating;
      message = state == TaskState.confirming ? '目标似乎已达到，请确认结果' : '等待你的操作';
      await announceGuidance(data);
      notifyListeners();
    } catch (e) {
      if (epoch == _epoch) {
        await pause();
        message = '$e';
        await tts.speak('暂时连不上导航服务，已暂停。请稍后点继续。');
        await bridge.invokeMethod('updateCompanion', {'text': message});
        notifyListeners();
        await feedback('client_error');
      }
    } finally {
      if (requestId == _requestId) {
        _busy = false;
        final pending = _pending;
        _pending = null;
        if (epoch == _epoch &&
            pending != null &&
            state == TaskState.navigating) {
          unawaited(_analyze(pending));
        } else if (epoch != _epoch && state == TaskState.navigating) {
          detector.reset();
        }
      }
    }
  }

  Future<void> announceGuidance(Map<String, dynamic> data) async {
    guidance = data['step_text'] as String;
    final page = (data['page_key'] as String?)?.trim();
    final pageKey = page != null && page.isNotEmpty
        ? page
        : '${data['app_key']}:${data['page_type']}';
    final key = data['target_key'] as String? ?? '';
    final role = data['target_role'];
    final target =
        '${data['action']}:${key.isNotEmpty
            ? key
            : role != null && role != 'other'
            ? role
            : guidance}';
    if (guidance == _spokenText) _spokenPage = pageKey;
    _pendingGuidance =
        guidance == _spokenText ||
            (pageKey == _spokenPage && target == _spokenTarget)
        ? null
        : {...data, '_page': pageKey, '_target': target};
    await bridge.invokeMethod('updateCompanion', {'text': guidance});
    await flushGuidance();
  }

  Future<void> flushGuidance() async {
    if (_flushingGuidance) return;
    final data = _pendingGuidance;
    if (data == null ||
        !{TaskState.navigating, TaskState.confirming}.contains(state)) {
      return;
    }
    final page = data['_page'] as String;
    _flushingGuidance = true;
    try {
      final started = await tts.speak(
        detailed
            ? '${data['step_text']} ${data['expected_result'] ?? ''}'
            : data['step_text'] as String,
        interrupt: _spokenPage.isNotEmpty && page != _spokenPage,
      );
      if (started && identical(data, _pendingGuidance)) {
        _spokenPage = page;
        _spokenTarget = data['_target'] as String;
        _spokenText = data['step_text'] as String;
        _pendingGuidance = null;
      }
    } finally {
      _flushingGuidance = false;
    }
  }

  Future<void> feedback(String kind) async {
    if (_token.isEmpty) return;
    final token = _token;
    final stepId = _stepId;
    await _loadOutbox();
    _outbox.add({
      'token': token,
      'feedback': kind,
      'step_id': stepId,
      'event_id': '${DateTime.now().microsecondsSinceEpoch}-$kind',
      'created_at': DateTime.now().millisecondsSinceEpoch,
    });
    await _saveOutbox();
    unawaited(retryFeedback());
  }

  Future<void> _loadOutbox() => _outboxReady ??= () async {
    final raw = await bridge.invokeMethod<String>('loadPendingFeedback');
    _outbox.addAll(
      (jsonDecode(raw ?? '[]') as List).map(
        (x) => Map<String, dynamic>.from(x as Map),
      ),
    );
    pendingFeedbackCount = _outbox.length;
  }();

  Future<void> _saveOutbox() {
    final json = jsonEncode(_outbox);
    _feedbackWork = _feedbackWork
        .catchError((_) {})
        .then(
          (_) => bridge.invokeMethod('savePendingFeedback', {'json': json}),
        );
    pendingFeedbackCount = _outbox.length;
    notifyListeners();
    return _feedbackWork;
  }

  Future<void> retryFeedback() async {
    await _loadOutbox();
    if (_flushing || _disposed) return;
    _flushing = true;
    try {
      while (_outbox.isNotEmpty && !_disposed) {
        final event = _outbox.first;
        if (DateTime.now().millisecondsSinceEpoch -
                (event['created_at'] as int) >
            86400000) {
          _outbox.removeAt(0);
        } else {
          try {
            await request('feedback', event, token: event['token'] as String);
            _outbox.removeAt(0);
          } catch (_) {
            message = '反馈已暂存，将在下次打开或开始任务时重试';
            break;
          }
        }
        await _saveOutbox();
      }
    } finally {
      _flushing = false;
    }
  }

  Future<void> pause() async {
    _pendingGuidance = null;
    ++_epoch;
    _pending = null;
    state = TaskState.paused;
    await tts.stop();
    await capture.stop();
    await bridge.invokeMethod('updateCompanion', {'text': '已暂停，点“暂停 / 继续”恢复'});
    message = '已暂停，继续时会重新查看画面';
    notifyListeners();
  }

  Future<void> resume() async {
    if (_token.isEmpty) return start(goal);
    if (_busy) {
      message = '上一帧正在结束，请稍候再继续';
      notifyListeners();
      return;
    }
    final epoch = ++_epoch;
    state = TaskState.authorizing;
    try {
      if (!await capture.requestPermission()) {
        state = TaskState.paused;
        notifyListeners();
        return;
      }
      if (epoch != _epoch) {
        await capture.stop();
        return;
      }
      await bridge.invokeMethod('moveToBackground');
      await Future<void>.delayed(const Duration(milliseconds: 450));
      if (epoch != _epoch) return;
      detector.reset();
      _spokenTarget = '';
      _spokenPage = '';
      _spokenText = '';
      guidance = '';
      state = TaskState.navigating;
      message = '重新查看当前画面';
      capture.startListening(_frame);
      notifyListeners();
    } catch (e) {
      state = TaskState.paused;
      message = '$e';
      notifyListeners();
    }
  }

  Future<void> finish(bool completed) async {
    await pause();
    await feedback(completed ? 'completed' : 'cancelled');
    _token = '';
    outcome = completed ? '你已确认完成' : '任务已结束，未确认完成';
    state = TaskState.ended;
    message = outcome;
    await bridge.invokeMethod('updateCompanion', {'text': outcome});
    notifyListeners();
  }

  Future<void> repeat() async {
    await tts.speak(guidance);
  }

  Future<void> help(String kind) async {
    ++_epoch;
    _pending = null;
    await feedback(kind);
    _spokenTarget = '';
    guidance = '';
    detector.reset();
    message = state == TaskState.paused ? '反馈已记录，点“继续”重新查看画面' : '正在重新确认下一步';
    notifyListeners();
  }

  @override
  void notifyListeners() {
    if (!_disposed) super.notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    tts.onComplete = null;
    _feedbackTimer.cancel();
    ++_epoch;
    capture.stop();
    client.close();
    tts.dispose();
    super.dispose();
  }
}
