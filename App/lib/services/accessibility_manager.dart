import 'dart:async';
import 'dart:convert';
import 'package:flutter/services.dart';

import '../models/accessibility_event.dart';

/// 无障碍服务管理
/// 不使用插件的静态 accessStream（单次注册广播接收器，cancel后无法重新注册），
/// 而是直接创建自己的 EventChannel，每次 listen 都会重新注册 BroadcastReceiver。
class AccessibilityServiceManager {
  StreamSubscription? _subscription;
  Timer? _debounceTimer;
  final List<AccessibilityEventData> _eventBuffer = [];

  /// 我们自己的 EventChannel，与插件使用相同的 channel name
  static const _eventChannel = EventChannel('com.intermap/accessibility_event');
  static const _nativeChannel = MethodChannel('com.intermap/app');

  /// 去抖后的事件回调
  void Function(AccessibilityEventData event)? onPageEvent;

  /// 原始事件回调（每次事件都触发，用于调试）
  void Function(AccessibilityEventData event)? onRawEvent;

  /// 调试日志回调
  void Function(String log)? onDebugLog;

  bool isListening = false;

  Future<bool> checkPermission() async {
    return await _nativeChannel.invokeMethod<bool>('trainingPermission') ?? false;
  }

  Future<void> requestPermission() async {
    await _nativeChannel.invokeMethod('requestTrainingPermission');
  }

  void startListening() {
    stopListening();

    isListening = true;
    _debug('开始监听无障碍事件（新EventChannel）...');

    _subscription = _eventChannel.receiveBroadcastStream().listen(
      _onEventData,
      onError: (e) => _debug('⚠ 流错误: $e'),
      onDone: () => _debug('⚠ 事件流结束'),
    );
  }

  /// 处理 EventChannel 传来的原始 JSON 字符串
  void _onEventData(dynamic rawData) {
    _debug('收到原始数据: ${rawData.runtimeType}');

    // 插件传过来的是 JSON 字符串
    Map<dynamic, dynamic> map;
    if (rawData is String) {
      try {
        map = jsonDecode(rawData) as Map<dynamic, dynamic>;
      } catch (e) {
        _debug('⚠ JSON解析失败: $e');
        return;
      }
    } else if (rawData is Map) {
      map = rawData;
    } else {
      _debug('⚠ 未知数据类型: ${rawData.runtimeType}');
      return;
    }

    final data = _parseRawEvent(map);
    if (data != null) {
      onRawEvent?.call(data);
      if (data.isPageChange || data.isClick) {
        _eventBuffer.add(data);
        _debounceEvent();
      }
    }
  }

  void _debug(String msg) {
    onDebugLog?.call('[${DateTime.now().toString().substring(11, 19)}] $msg');
  }

  void stopListening() {
    _subscription?.cancel();
    _subscription = null;
    _debounceTimer?.cancel();
    _eventBuffer.clear();
    isListening = false;
  }

  void _debounceEvent() {
    _debounceTimer?.cancel();
    _debounceTimer = Timer(const Duration(milliseconds: 300), () {
      if (_eventBuffer.isEmpty) return;
      final pageChange = _eventBuffer.lastWhere(
        (e) => e.isPageChange,
        orElse: () => _eventBuffer.last,
      );
      _eventBuffer.clear();
      onPageEvent?.call(pageChange);
    });
  }

  AccessibilityEventData? _parseRawEvent(Map<dynamic, dynamic> map) {
    // 事件类型
    int eventType = 0;
    final et = map['eventType'];
    _debug('eventType=$et (${et.runtimeType})');
    if (et is int) {
      eventType = et;
    } else if (et is num) {
      eventType = et.toInt();
    } else if (et != null) {
      _debug('⚠ eventType类型不对: ${et.runtimeType}');
    }

    // 包名（某些系统事件可能无包名，不丢弃）
    final pnRaw = map['packageName'];
    var pn = pnRaw?.toString() ?? '';
    if (pn == 'null') pn = '';
    _debug('packageName="$pn"');
    if (pn.isEmpty) pn = 'unknown';

    // 当前节点文本
    String? text;
    final ct = map['capturedText'];
    if (ct != null && ct.toString() != 'null' && ct.toString().isNotEmpty) {
      text = ct.toString();
    }

    // 提取所有子节点文本
    final texts = <String>[];
    _extractTexts(map['subNodesActions'], texts);
    if (text != null && !texts.contains(text)) {
      texts.insert(0, text);
    }
    _debug('提取文本数: ${texts.length}, 内容: ${texts.take(5)}');

    // 节点ID
    String? viewId;
    final nid = map['nodeId'];
    if (nid != null && nid.toString() != 'null') {
      viewId = nid.toString();
    }

    // 是否可点击
    bool isClickable = false;
    final cl = map['isClickable'];
    if (cl is bool) isClickable = cl;

    _debug('✓ 解析成功: type=$eventType pkg=$pn texts=${texts.length}');

    return AccessibilityEventData(
      eventType: eventType,
      packageName: pn,
      text: text,
      viewId: viewId,
      isClickable: isClickable,
      windowTexts: texts,
      textSignature: texts.join('|'),
    );
  }

  void _extractTexts(dynamic node, List<String> texts) {
    if (node is! List) return;
    for (final item in node) {
      if (item is! Map) continue;
      final ct = item['capturedText'];
      if (ct != null &&
          ct.toString() != 'null' &&
          ct.toString().isNotEmpty &&
          !texts.contains(ct.toString())) {
        texts.add(ct.toString());
      }
      _extractTexts(item['subNodesActions'], texts);
    }
  }

  void dispose() {
    stopListening();
    _debounceTimer?.cancel();
  }
}
