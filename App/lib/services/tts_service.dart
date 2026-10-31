import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// TTS 语音播报服务
class TTSService {
  final FlutterTts _tts = FlutterTts();
  static const MethodChannel _nativeChannel = MethodChannel('com.intermap/app');
  bool _initialized = false;
  double _speechRate = 0.46; // 放慢一点，减少机械感
  double _pitch = 1.08;
  final String _currentLanguage = 'zh-CN';

  Future<void> init() async {
    if (_initialized) return;

    await _tts.setLanguage(_currentLanguage);
    await _tts.setSpeechRate(_speechRate);
    await _tts.setPitch(_pitch);
    await _tts.setVolume(1.0);
    await _tts.awaitSpeakCompletion(false);
    // 尝试设置中文女声
    try {
      await _tts.setVoice({'name': 'zh-CN', 'locale': 'zh-CN'});
    } catch (_) {
      // 部分 Android TTS 引擎不接受按 name 设置中文语音，保留语言设置即可。
    }

    _initialized = true;
  }

  /// 播报文本
  Future<void> speak(String text) async {
    if (text.trim().isEmpty) return;

    // 清理特殊字符
    final cleaned = text.replaceAll(
      RegExp(r'''[^\u4e00-\u9fa5a-zA-Z0-9\s，。！？、：；“”"'\(\)（）《》\-+]'''),
      '',
    );

    if (cleaned.trim().isEmpty) return;

    if (defaultTargetPlatform == TargetPlatform.android) {
      final nativeSpoken = await _speakWithNativeAndroid(cleaned);
      if (nativeSpoken) return;
    }

    try {
      if (!_initialized) await init();
      final result = await _tts.speak(cleaned);
      if (!_isSpeakSuccess(result)) {
        await _speakWithNativeAndroid(cleaned);
      }
    } catch (e) {
      await _speakWithNativeAndroid(cleaned);
    }
  }

  bool _isSpeakSuccess(dynamic result) {
    return result == 1 || result == '1' || result == true;
  }

  Future<bool> _speakWithNativeAndroid(String text) async {
    if (defaultTargetPlatform != TargetPlatform.android) return false;
    try {
      final ok = await _nativeChannel.invokeMethod<bool>('speakNative', {
        'text': text,
        'speechRate': _speechRate,
        'pitch': _pitch,
      });
      return ok == true;
    } catch (_) {
      return false;
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
