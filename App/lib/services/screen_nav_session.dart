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
  bool _isActive = false;
  bool _isNavigating = false;
  bool _isComplete = false;

  String _currentGuidance = '';
  String _lastSpokenText = '';
  DateTime? _lastSpokenTime;
  DateTime? _nodeEnterTime;
  int _stuckLevel = 0;
  GuidanceStyle _guidanceStyle = GuidanceStyle.concise;

  bool _isAnalyzing = false; // 防止并发 API 调用
  final List<Map<String, String>> _apiHistory = [];

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
    _lastSpokenTime = null;
  }

  /// 请求截屏权限并开始导航
  Future<bool> start({required String app, required String task}) async {
    _task = task;
    _apiHistory.clear();
    _currentGuidance = '';
    _lastSpokenText = '';
    _stuckLevel = 0;
    _isComplete = false;
    _isNavigating = false;

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

    _capture.startListening(_onFrame);

    // 延迟回到桌面（用 MethodChannel，不会销毁 Activity）
    await Future.delayed(const Duration(milliseconds: 500));
    try {
      const channel = MethodChannel('com.intermap/app');
      await channel.invokeMethod('moveToBackground');
    } catch (_) {}

    return true;
  }

  /// 处理每一帧
  void _onFrame(String base64Frame) {
    if (!_isActive || _isComplete) return;
    if (_isAnalyzing) return; // 上一次 API 还没返回，跳过

    // 画面变化检测 + 频率控制
    if (!_changeDetector.shouldAnalyze(base64Frame)) return;

    _debug('画面有变化，调用 API 识别...');
    _isAnalyzing = true;
    _analyzeFrame(base64Frame).then((_) {
      _isAnalyzing = false;
    });
  }

  /// 调用 API 识别画面
  Future<void> _analyzeFrame(String base64Frame) async {
    final result = await _api.analyze(
      base64Image: base64Frame,
      task: _task,
      history: _apiHistory.take(3).toList(),
    );

    if (result == null) {
      _debug('API 返回 null');
      return;
    }

    final ok = result['ok'];
    if (ok != true) {
      _debug('API 识别失败: ${result['error']}');
      return;
    }

    // 提取引导信息
    final thought = result['thought']?.toString() ?? '';
    final action = result['action']?.toString() ?? '';
    final actionType = result['action_type']?.toString() ?? '';

    _debug('API 结果: action="$action" type=$actionType');

    // 构建引导文本
    final guidance = GuidanceFormatter.fromModel(
      action: actionType == 'click' ? action : '',
      thought: thought,
      style: _guidanceStyle,
    );

    // 更新历史
    if (action.isNotEmpty) {
      _apiHistory.insert(0, {'role': 'assistant', 'content': action});
      if (_apiHistory.length > 6) _apiHistory.removeLast();
    }

    // 语音去重
    if (_isDuplicateSpeech(guidance)) {
      _debug('语音去重，跳过');
      return;
    }

    // 更新状态
    _nodeEnterTime = DateTime.now();
    _stuckLevel = 0;
    _currentGuidance = guidance;
    _lastSpokenText = guidance;
    _lastSpokenTime = DateTime.now();

    _onGuidance?.call(guidance, []);
    _tts.speak(guidance);
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
    _stuckLevel = 0;
    _nodeEnterTime = null;
    _apiHistory.clear();
    _changeDetector.reset();
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

  void _notifyStatus() {
    _onStatusChange?.call();
  }
}
