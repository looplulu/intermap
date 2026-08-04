import 'dart:async';
import 'package:flutter/services.dart';
import 'screen_capture_service.dart';
import 'tts_service.dart';
import 'hd_map.dart';
import 'guidance_style.dart';

/// 录屏模式导航会话
/// 截屏 → 帧变化检测 → UI-TARS API 识别 → 生成引导
class ScreenNavSession {
  final ScreenCaptureManager _capture = ScreenCaptureManager();
  final UiTarsClient _api = UiTarsClient();
  final FrameChangeDetector _changeDetector = FrameChangeDetector();
  TTSService _tts;

  void Function(String guidance, List<String> risks)? _onGuidance;
  void Function(String log)? _onDebugLog;
  void Function()? _onStatusChange;
  void Function()? _onComplete;

  String _task = '';
  String _app = '';
  bool _isActive = false;
  bool _isNavigating = false;
  bool _isComplete = false;

  String _currentGuidance = '';
  String _lastSpokenText = '';
  DateTime? _lastSpokenTime;
  DateTime? _nodeEnterTime;
  int _stuckLevel = 0;
  GuidanceStyle _guidanceStyle = GuidanceStyle.concise;
  final PageIdentityStabilizer _pageStabilizer = PageIdentityStabilizer();
  final GuidanceTargetStabilizer _targetStabilizer = GuidanceTargetStabilizer();

  bool _isAnalyzing = false; // 防止并发 API 调用
  String? _pendingCloudFrame;
  final List<Map<String, String>> _apiHistory = [];
  String _diagnosticSessionId = '';

  // 状态
  bool get isActive => _isActive;
  bool get isNavigating => _isNavigating;
  bool get isComplete => _isComplete;
  String get currentGuidance => _currentGuidance;
  String get task => _task;

  static const Duration _stuckThreshold = Duration(seconds: 8);

  // ignore: prefer_initializing_formals
  ScreenNavSession({required TTSService tts}) : _tts = tts;

  void setDependencies({
    required HDMap hdMap,
    void Function(String guidance, List<String> risks)? onGuidance,
    void Function(String log)? onDebugLog,
    void Function()? onStatusChange,
    void Function()? onComplete,
  }) {
    _onGuidance = onGuidance;
    _onDebugLog = onDebugLog;
    _onStatusChange = onStatusChange;
    _onComplete = onComplete;
  }

  void setTts(TTSService tts) {
    _tts = tts;
  }

  void setGuidanceStyle(GuidanceStyle style) {
    _guidanceStyle = style;
    _lastSpokenText = '';
    _pageStabilizer.reset();
    _targetStabilizer.reset();
    _lastSpokenTime = null;
  }

  /// 请求截屏权限并开始导航
  Future<bool> start({required String app, required String task}) async {
    _app = app;
    _task = task;
    _diagnosticSessionId =
        'nav_${DateTime.now().millisecondsSinceEpoch.toString()}';
    _apiHistory.clear();
    _currentGuidance = '';
    _lastSpokenText = '';
    _stuckLevel = 0;
    _pageStabilizer.reset();
    _targetStabilizer.reset();
    _isComplete = false;
    _isNavigating = false;
    _isAnalyzing = false;
    _pendingCloudFrame = null;

    _debug('请求截屏权限...');
    _notifyStatus();

    final granted = await _capture.requestPermission();
    if (!granted) {
      _debug('用户拒绝了录屏权限');
      return false;
    }

    _debug('截屏权限已获取，开始监听帧...');
    _isActive = true;
    _isNavigating = true;
    _notifyStatus();

    _sendDiagnostic('navigation_started', {'capture_mode': 'android_screen'});

    // 先离开小路，再开始取帧，避免把导航状态页误认为目标 App。
    try {
      const channel = MethodChannel('com.intermap/app');
      await channel.invokeMethod('moveToBackground');
    } catch (_) {}
    await Future.delayed(const Duration(milliseconds: 450));
    _capture.startListening(_onFrame);

    return true;
  }

  /// 处理每一帧
  void _onFrame(String base64Frame) {
    if (!_isActive || _isComplete) return;
    if (!_changeDetector.shouldAnalyze(base64Frame)) return;

    _queueCloudAnalysis(base64Frame);
  }

  void _queueCloudAnalysis(String frame) {
    if (_isAnalyzing) {
      _pendingCloudFrame = frame;
      return;
    }
    _isAnalyzing = true;
    _debug('画面有变化，调用视觉 API 识别...');
    _analyzeFrame(frame).whenComplete(() {
      _isAnalyzing = false;
      final pending = _pendingCloudFrame;
      _pendingCloudFrame = null;
      if (pending != null && _isActive && !_isComplete) {
        _queueCloudAnalysis(pending);
      }
    });
  }

  /// 调用 API 识别画面
  Future<void> _analyzeFrame(String base64Frame) async {
    final result = await _api.analyze(
      base64Image: base64Frame,
      app: _app,
      task: _task,
      history: _apiHistory.take(3).toList(),
    );

    if (result == null) {
      _debug('API 返回 null');
      _sendDiagnostic('api_error', {'error': 'null_response'});
      return;
    }

    final ok = result['ok'];
    if (ok != true) {
      _debug('API 识别失败: ${result['error']}');
      _sendDiagnostic('api_error', {
        'error': result['error']?.toString() ?? 'unknown',
        'duration_ms': result['_duration_ms'] ?? 0,
        'http_status': result['_http_status'] ?? 0,
      });
      return;
    }

    // 提取引导信息
    final thought = result['thought']?.toString() ?? '';
    final action = result['action']?.toString() ?? '';
    final actionType = result['action_type']?.toString() ?? '';
    final structuredPageName = result['page_name']?.toString().trim() ?? '';
    final pageName = structuredPageName.isNotEmpty
        ? structuredPageName
        : GuidanceFormatter.extractPageName(thought);
    final structuredPageKey = result['page_key']?.toString().trim() ?? '';
    final normalizedPageName = GuidanceFormatter.normalizePageKey(pageName);
    final pageKey = normalizedPageName.isNotEmpty
        ? normalizedPageName
        : structuredPageKey;

    _debug('API 结果: page="$pageName" action="$action" type=$actionType');

    // 构建引导文本
    final guidance = GuidanceFormatter.fromModel(
      action: actionType == 'click' ? action : '',
      thought: thought,
      style: _guidanceStyle,
    );

    _sendDiagnostic('api_result', {
      'page_name': pageName,
      'page_key': pageKey,
      'guidance': guidance,
      'action_type': actionType,
      'duration_ms': result['_duration_ms'] ?? 0,
      'http_status': result['_http_status'] ?? 200,
      'confidence': result['confidence'] ?? 0,
    });

    final pageChanged = _pageStabilizer.shouldAnnounce(pageKey);
    final targetCorrected =
        !pageChanged && _targetStabilizer.shouldCorrect(guidance);
    if (!pageChanged && !targetCorrected) {
      _debug('页面身份未变化，保留当前引导');
      _sendDiagnostic('guidance_suppressed', {
        'reason': 'same_page',
        'page_name': pageName,
        'page_key': pageKey,
      });
      return;
    }

    if (action.isNotEmpty) {
      _apiHistory.insert(0, {'role': 'assistant', 'content': action});
      if (_apiHistory.length > 6) _apiHistory.removeLast();
    }

    // 语音去重
    if (!targetCorrected && _isDuplicateSpeech(guidance)) {
      _debug('语音去重，跳过');
      _sendDiagnostic('guidance_suppressed', {
        'reason': 'similar_guidance',
        'page_name': pageName,
        'page_key': pageKey,
      });
      return;
    }

    // 更新状态
    _nodeEnterTime = DateTime.now();
    _stuckLevel = 0;
    _currentGuidance = guidance;
    _lastSpokenText = guidance;
    _lastSpokenTime = DateTime.now();
    _targetStabilizer.accept(guidance);

    _onGuidance?.call(guidance, []);
    _tts.speak(guidance);
    _sendDiagnostic('guidance_announced', {
      'page_name': pageName,
      'page_key': pageKey,
      'guidance': guidance,
      'action_type': actionType,
    });
    _debug('引导已输出: $guidance');
    _notifyStatus();
  }

  /// 定时器：卡住检测，由 UI 层每秒调用
  void tick() {
    if (!_isNavigating || _nodeEnterTime == null || _isComplete) return;

    final stuck = DateTime.now().difference(_nodeEnterTime!);
    if (stuck < _stuckThreshold) return;

    _stuckLevel++;
    _nodeEnterTime = DateTime.now(); // 重置计时

    String escalated;
    if (_stuckLevel == 1) {
      escalated = '$_currentGuidance，仔细找一下屏幕上的按钮';
    } else if (_stuckLevel == 2) {
      escalated = '$_currentGuidance，找不到就看看屏幕上下方有没有';
    } else {
      escalated = '如果实在找不到，点左上角返回，重新来';
    }

    if (!_isDuplicateSpeech(escalated)) {
      _lastSpokenText = escalated;
      _lastSpokenTime = DateTime.now();
      _onGuidance?.call(escalated, []);
      _tts.speak(escalated);
    }

    if (_stuckLevel >= 4) {
      // 4次升级后停止
      complete();
    }
  }

  void complete() {
    _isComplete = true;
    _isNavigating = false;
    _tts.speak('导航已结束');
    _onComplete?.call();
    _notifyStatus();
  }

  /// 停止导航
  Future<void> stop() async {
    await _capture.stop();
    _isActive = false;
    _isNavigating = false;
    _isComplete = true;
    _changeDetector.reset();
    _pendingCloudFrame = null;
    _notifyStatus();
  }

  /// 重置
  void reset() {
    _capture.stop();
    _isActive = false;
    _isNavigating = false;
    _isComplete = false;
    _currentGuidance = '';
    _lastSpokenText = '';
    _pageStabilizer.reset();
    _targetStabilizer.reset();
    _stuckLevel = 0;
    _nodeEnterTime = null;
    _apiHistory.clear();
    _changeDetector.reset();
    _pendingCloudFrame = null;
    _notifyStatus();
  }

  bool _isDuplicateSpeech(String newText) {
    if (_lastSpokenText.isEmpty || _lastSpokenTime == null) return false;
    if (DateTime.now().difference(_lastSpokenTime!).inSeconds < 15) {
      if (_similarity(_lastSpokenText, newText) >= 0.7) return true;
    }
    return false;
  }

  double _similarity(String a, String b) {
    if (a.isEmpty || b.isEmpty) return 0.0;
    final setA = a.runes.toSet();
    final setB = b.runes.toSet();
    final intersection = setA.intersection(setB).length;
    final union = setA.union(setB).length;
    return union == 0 ? 0.0 : intersection / union;
  }

  void _debug(String msg) {
    _onDebugLog?.call('[${DateTime.now().toString().substring(11, 19)}] $msg');
  }

  void _sendDiagnostic(String eventType, Map<String, dynamic> payload) {
    if (_diagnosticSessionId.isEmpty) return;
    unawaited(
      _api.sendDiagnostic({
        'session_id': _diagnosticSessionId,
        'event_type': eventType,
        'timestamp': DateTime.now().toIso8601String(),
        'app': _app.isEmpty ? 'douyin' : _app,
        'payload': payload,
      }),
    );
  }

  void _notifyStatus() {
    _onStatusChange?.call();
  }
}
