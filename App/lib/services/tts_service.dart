import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// TTS 语音播报服务
class TTSService {
  final FlutterTts _tts = FlutterTts();
  static const MethodChannel _nativeChannel = MethodChannel('com.intermap/app');
  bool _initialized = false;
  bool _fallbackSpeaking = false;
  VoidCallback? onComplete;
  double _speechRate = 0.46; // 放慢一点，减少机械感
  double _pitch = 1.0;
  final String _currentLanguage = 'zh-CN';

  Future<void> init() async {
    if (_initialized) return;

    await _tts.setLanguage(_currentLanguage);
    await _tts.setSpeechRate(_speechRate);
    await _tts.setPitch(_pitch);
    await _tts.setVolume(1.0);
    await _tts.awaitSpeakCompletion(false);
    void finished() {
      _fallbackSpeaking = false;
      onComplete?.call();
    }

    _tts.setCompletionHandler(finished);
    _tts.setCancelHandler(finished);
    _tts.setErrorHandler((_) => finished());
    // 尝试设置中文女声
    try {
      await _tts.setVoice({'name': 'zh-CN', 'locale': 'zh-CN'});
    } catch (_) {
      // 部分 Android TTS 引擎不接受按 name 设置中文语音，保留语言设置即可。
    }

    _initialized = true;
  }

  /// 播报文本
  Future<bool> speak(String text, {bool interrupt = true}) async {
    if (!interrupt && _fallbackSpeaking) return false;
    if (interrupt && _fallbackSpeaking) await _tts.stop();
    if (text.trim().isEmpty) return false;

    // 清理特殊字符
    final cleaned = text.replaceAll(
      RegExp(r'''[^\u4e00-\u9fa5a-zA-Z0-9\s，。！？、：；“”"'\(\)（）《》\-+]'''),
      '',
    );

    if (cleaned.trim().isEmpty) return false;

    if (defaultTargetPlatform == TargetPlatform.android) {
      final nativeSpoken = await _speakWithNativeAndroid(
        cleaned,
        interrupt: interrupt,
      );
      if (nativeSpoken == 'busy') return false;
      if (nativeSpoken == 'started') return true;
    }

    try {
      if (!_initialized) await init();
      _fallbackSpeaking = true;
      final result = await _tts.speak(cleaned);
      if (!_isSpeakSuccess(result)) {
        _fallbackSpeaking = false;
        return await _speakWithNativeAndroid(cleaned, interrupt: interrupt) ==
            'started';
      }
      return true;
    } catch (e) {
      _fallbackSpeaking = false;
      return await _speakWithNativeAndroid(cleaned, interrupt: interrupt) ==
          'started';
    }
  }

  bool _isSpeakSuccess(dynamic result) {
    return result == 1 || result == '1' || result == true;
  }

  Future<String> _speakWithNativeAndroid(
    String text, {
    required bool interrupt,
  }) async {
    if (defaultTargetPlatform != TargetPlatform.android) return 'unavailable';
    try {
      final ok = await _nativeChannel.invokeMethod<dynamic>('speakNative', {
        'text': text,
        'speechRate': (_speechRate * 2).clamp(0.2, 1.5),
        'pitch': _pitch,
        'interrupt': interrupt,
      });
      return ok == 'busy'
          ? 'busy'
          : ok == true
          ? 'started'
          : 'unavailable';
    } catch (_) {
      return 'unavailable';
    }
  }

  /// 停止播报
  Future<void> stop() async {
    await _nativeChannel.invokeMethod('stopNativeTts').catchError((_) {});
    await _tts.stop();
  }

  /// 暂停
  Future<void> pause() async {
    await _tts.pause();
  }

  /// 设置语速 (0.0 - 1.0)
  Future<void> setSpeechRate(double rate) async {
    _speechRate = rate.clamp(0.1, 1.0);
    await _tts.setSpeechRate(_speechRate);
  }

  /// 设置音调 (0.5 - 2.0)
  Future<void> setPitch(double pitch) async {
    _pitch = pitch.clamp(0.5, 2.0);
    await _tts.setPitch(_pitch);
  }

  void dispose() {
    _nativeChannel.invokeMethod('stopNativeTts').catchError((_) {});
    _tts.stop().catchError((_) => 0);
  }
}
