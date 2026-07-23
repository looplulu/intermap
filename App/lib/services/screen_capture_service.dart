import 'dart:async';
import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

/// 屏幕截图管理器
/// 通过 MediaProjection + EventChannel 获取实时屏幕帧（base64 JPEG）
class ScreenCaptureManager {
  static const _methodChannel = MethodChannel('com.intermap/app');
  static const _eventChannel = EventChannel('com.intermap/capture_event');

  StreamSubscription? _frameSubscription;
  bool _isCapturing = false;

  /// 截屏权限请求结果
  Future<bool> requestPermission() async {
    try {
      final result = await _methodChannel.invokeMethod<bool>(
        'requestScreenCapture',
      );
      if (result == true) {
        _isCapturing = true;
      }
      return result ?? false;
    } catch (e) {
      return false;
    }
  }

  /// 开始接收截屏帧，返回帧的 Stream
  Stream<String> get frameStream {
    return _eventChannel.receiveBroadcastStream().map(
      (frame) => frame as String,
    );
  }

  /// 开始截帧监听
  void startListening(void Function(String base64Frame) onFrame) {
    stopListening();
    _frameSubscription = frameStream.listen(onFrame);
  }

  /// 停止截屏
  Future<void> stop() async {
    stopListening();
    try {
      await _methodChannel.invokeMethod('stopScreenCapture');
    } catch (_) {}
    _isCapturing = false;
  }

  void stopListening() {
    _frameSubscription?.cancel();
    _frameSubscription = null;
  }

  bool get isCapturing => _isCapturing;
}

/// UI-TARS API 客户端
/// 复刻网页端 /intermap/api/ui-tars 端点
class UiTarsClient {
  static const String _baseUrl = 'https://loop-lulu.com/intermap/api/ui-tars';

  /// 调用 UI-TARS 分析屏幕截图
  /// 返回 API 的原始 JSON 响应
  Future<Map<String, dynamic>?> analyze({
    required String base64Image,
    required String task,
    int? imageWidth,
    int? imageHeight,
    List<Map<String, String>> history = const [],
  }) async {
    try {
      final requestBody = <String, dynamic>{
        'image': 'data:image/jpeg;base64,$base64Image',
        'task': '用户的目标是: "$task"。请识别当前页面，判断用户在完成目标过程中的哪一步。',
        'history': history,
      };
      if (imageWidth != null) {
        requestBody['image_width'] = imageWidth;
      }
      if (imageHeight != null) {
        requestBody['image_height'] = imageHeight;
      }
      final body = jsonEncode(requestBody);

      final response = await http
          .post(
            Uri.parse(_baseUrl),
            headers: {'Content-Type': 'application/json'},
            body: body,
          )
          .timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        return jsonDecode(response.body) as Map<String, dynamic>;
      } else {
        return {'ok': false, 'error': 'HTTP ${response.statusCode}'};
      }
    } catch (e) {
      return {'ok': false, 'error': e.toString()};
    }
  }
}

/// 画面变化检测器
/// 通过帧哈希快速判断屏幕是否有变化，避免重复 API 调用
class FrameChangeDetector {
  int _lastHash = 0;
  DateTime? _lastAnalyzeTime;
  final Duration _minInterval;

  /// 上次分析的时间戳
  DateTime? get lastAnalyzeTime => _lastAnalyzeTime;

  FrameChangeDetector({Duration? minInterval})
    : _minInterval = minInterval ?? const Duration(milliseconds: 1500);

  /// 判断是否需要分析新帧
  /// 返回 true 表示画面有变化且距上次分析已过间隔
  bool shouldAnalyze(String base64Frame) {
    // 简单哈希：取 base64 中间一段计算
    final hash = _quickHash(base64Frame);

    // 距离上次分析时间不足，跳过
    final now = DateTime.now();
    if (_lastAnalyzeTime != null &&
        now.difference(_lastAnalyzeTime!) < _minInterval) {
      return false;
    }

    // 画面没变化，跳过
    if (hash == _lastHash) {
      return false;
    }

    _lastHash = hash;
    _lastAnalyzeTime = now;
    return true;
  }

  /// 快速哈希（采样 base64 字符串的一部分）
  int _quickHash(String s) {
    if (s.length < 100) return s.hashCode;
    var hash = 0;
    // 每 16 个字符采样一个
    for (var i = 0; i < s.length; i += 16) {
      hash = ((hash << 5) - hash + s.codeUnitAt(i)) | 0;
    }
    return hash;
  }

  void reset() {
    _lastHash = 0;
    _lastAnalyzeTime = null;
  }
}
