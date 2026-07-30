import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';

import '../models/accessibility_event.dart';

/// 训练事件记录
class TrainingEvent {
  final DateTime timestamp;
  final int eventType;
  final String packageName;
  final String? text;
  final String? viewId;
  final List<String> windowTexts;
  final String textSignature;
  final bool isPageChange;
  final String? annotation;
  final String source;
  final String? actionType;

  TrainingEvent({
    required this.timestamp,
    required this.eventType,
    required this.packageName,
    this.text,
    this.viewId,
    this.windowTexts = const [],
    this.textSignature = '',
    this.isPageChange = false,
    this.annotation,
    this.source = 'accessibility',
    this.actionType,
  });

  Map<String, dynamic> toJson() => {
    'timestamp': timestamp.millisecondsSinceEpoch,
    'event_type': eventType,
    'package_name': packageName,
    'text': text,
    'view_id': viewId,
    'window_texts': windowTexts,
    'text_signature': textSignature,
    'is_page_change': isPageChange,
    'annotation': annotation,
    'source': source,
    'action_type': actionType,
  };
}

/// 推断的节点
class InferredNode {
  final String nodeId;
  final String pageType;
  final String pageName;
  final List<String> keyTexts;
  final DateTime firstSeen;
  double confidence;
  int visitCount;

  InferredNode({
    required this.nodeId,
    required this.pageType,
    required this.pageName,
    required this.keyTexts,
    required this.firstSeen,
    this.confidence = 0.0,
    this.visitCount = 1,
  });

  Map<String, dynamic> toJson() => {
    'node_id': nodeId,
    'page_type': pageType,
    'page_name': pageName,
    'key_texts': keyTexts,
    'first_seen': firstSeen.toIso8601String(),
    'confidence': confidence,
    'visit_count': visitCount,
  };
}

/// 训练会话状态
enum TrainSessionStatus { idle, recording, paused, completed }

/// 训练会话管理器
class TrainingSessionManager {
  String? _app;
  String? _task;
  String _sessionId = '';
  TrainSessionStatus _status = TrainSessionStatus.idle;
  DateTime? _startedAt;
  DateTime? _endedAt;

  final List<TrainingEvent> _events = [];
  final List<InferredNode> _nodes = [];
  final List<Map<String, dynamic>> _annotations = [];
  final List<Map<String, dynamic>> _canonicalEvents = [];

  String? _lastSignature;
  String? _currentNodeId;
  String? _previousNodeId;
  String _captureMode = 'android_screen';
  String _lastSuggestedAction = '';
  int _eventSequence = 0;
  Timer? _checkpointTimer;
  bool _uploaded = false;

  void Function()? onStatusChange;
  void Function(String log)? onLog;
  void Function(String nodeId)? onNodeChange;

  TrainSessionStatus get status => _status;
  String get sessionId => _sessionId;
  String? get app => _app;
  String? get task => _task;
  List<TrainingEvent> get events => List.unmodifiable(_events);
  List<InferredNode> get nodes => List.unmodifiable(_nodes);
  List<Map<String, dynamic>> get canonicalEvents =>
      List.unmodifiable(_canonicalEvents);
  int get eventCount => _events.length;
  int get nodeCount => _nodes.length;
  int get annotationCount => _annotations.length;
  String? get currentNodeId => _currentNodeId;

  void start({
    required String app,
    required String task,
    String captureMode = 'android_screen',
  }) {
    _app = app;
    _task = task;
    _captureMode = captureMode;
    _sessionId = DateTime.now().millisecondsSinceEpoch.toString();
    _status = TrainSessionStatus.recording;
    _startedAt = DateTime.now();
    _events.clear();
    _nodes.clear();
    _annotations.clear();
    _canonicalEvents.clear();
    _lastSignature = null;
    _currentNodeId = null;
    _previousNodeId = null;
    _lastSuggestedAction = '';
    _eventSequence = 0;
    _uploaded = false;
    _recordCanonical('session_start', {
      'mode': task == 'free_exploration' ? 'learn' : 'goal_feedback',
    });
    _scheduleCheckpoint();
    onStatusChange?.call();
    _log('训练开始: $app - $task');
  }

  void stop() {
    if (_status == TrainSessionStatus.completed) return;
    _status = TrainSessionStatus.completed;
    _endedAt = DateTime.now();
    _recordCanonical('session_end', {
      'event_count': _events.length,
      'node_count': _nodes.length,
      'annotation_count': _annotations.length,
    });
    _checkpointTimer?.cancel();
    unawaited(saveToFile());
    onStatusChange?.call();
    _log('训练结束，共 ${_events.length} 个事件，${_nodes.length} 个节点');
  }

  void pause() {
    if (_status == TrainSessionStatus.recording) {
      _status = TrainSessionStatus.paused;
      onStatusChange?.call();
      _log('训练已暂停');
    }
  }

  void resume() {
    if (_status == TrainSessionStatus.paused) {
      _status = TrainSessionStatus.recording;
      onStatusChange?.call();
      _log('训练已恢复');
    }
  }

  void handleEvent(AccessibilityEventData event) {
    if (_status != TrainSessionStatus.recording) return;

    final texts = event.windowTexts;
    final signature = event.textSignature.isNotEmpty
        ? event.textSignature
        : texts.join('|');
    final isPageChange =
        event.isPageChange ||
        (_lastSignature != null &&
            _lastSignature != signature &&
            signature.isNotEmpty);

    final te = TrainingEvent(
      timestamp: DateTime.now(),
      eventType: event.eventType,
      packageName: event.packageName,
      text: event.text,
      viewId: event.viewId,
      windowTexts: texts,
      textSignature: signature.isNotEmpty ? signature : '',
      isPageChange: isPageChange,
    );
    _events.add(te);
    _recordCanonical('accessibility_observed', {
      'event_type': event.eventType,
      'package_name': event.packageName,
      'text': event.text,
      'view_id': event.viewId,
      'ocr_texts': texts.take(40).toList(),
      'page_signature': signature,
      'is_page_change': isPageChange,
    });

    if (isPageChange && signature.isNotEmpty) {
      _lastSignature = signature;
      final node = _inferNode(event, texts);
      _recordNodeObservation(node, signature, texts);
    }

    _scheduleCheckpoint();
    _log('事件: ${event.eventTypeLabel} | ${event.packageName}');
  }

  void handleScreenObservation({
    required String pageSummary,
    required List<String> keyTexts,
    String action = '',
    String actionType = '',
    String pageName = '',
    double confidence = 0.0,
    List<String> amounts = const [],
  }) {
    if (_status != TrainSessionStatus.recording) return;

    final texts = keyTexts.isNotEmpty
        ? keyTexts
        : [pageSummary, action].where((t) => t.trim().isNotEmpty).toList();
    final signature = texts.take(8).join('|');
    final isPageChange =
        _lastSignature == null ||
        (_lastSignature != signature && signature.isNotEmpty);

    final event = TrainingEvent(
      timestamp: DateTime.now(),
      eventType: -100,
      packageName: _app ?? 'screen',
      text: pageSummary,
      windowTexts: texts,
      textSignature: signature,
      isPageChange: isPageChange,
      source: 'screen',
      actionType: actionType.isEmpty ? null : actionType,
      annotation: action.isEmpty ? null : action,
    );
    _events.add(event);
    _recordCanonical('ocr_observed', {
      'page_name': pageName,
      'page_summary': pageSummary,
      'ocr_texts': texts.take(40).toList(),
      'page_signature': signature,
      'suggested_action': action,
      'action_type': actionType,
      'confidence': confidence,
      'amounts': amounts,
    });

    if (isPageChange && signature.isNotEmpty) {
      _lastSignature = signature;
      final node = _inferScreenNode(
        texts,
        pageSummary,
        pageName,
        confidence,
      );
      _recordNodeObservation(node, signature, texts);
    }

    if (action.isNotEmpty) _lastSuggestedAction = action;
    _scheduleCheckpoint();
    final label = action.isEmpty ? pageSummary : action;
    _log('录屏观察: ${label.isEmpty ? "页面变化" : label}');
  }

  InferredNode _inferNode(
    AccessibilityEventData event,
    List<String> texts,
  ) {
    final existing = _nodes.indexWhere((n) {
      // 简单匹配：关键文本高度重合
      final overlap = n.keyTexts.where((t) => texts.contains(t)).length;
      return overlap >= 3;
    });

    if (existing >= 0) {
      _nodes[existing].visitCount++;
      _currentNodeId = _nodes[existing].nodeId;
      onNodeChange?.call(_currentNodeId!);
      return _nodes[existing];
    }

    final keyTexts = texts.take(10).toList();
    final pageType = _inferPageType(keyTexts);
    final pageName = _inferPageTypeLabel(pageType);
    final nodeId = _stableNodeId(pageType, pageName, keyTexts);

    final node = InferredNode(
      nodeId: nodeId,
      pageType: pageType,
      pageName: pageName,
      keyTexts: keyTexts,
      firstSeen: DateTime.now(),
    );
    _nodes.add(node);
    _currentNodeId = nodeId;
    onNodeChange?.call(nodeId);
    _log('发现新节点: $nodeId ($pageType)');
    return node;
  }

  InferredNode _inferScreenNode(
    List<String> texts,
    String pageSummary,
    String pageName,
    double confidence,
  ) {
    final existing = _nodes.indexWhere((n) {
      final overlap = n.keyTexts.where((t) => texts.contains(t)).length;
      final sameName =
          pageName.isNotEmpty &&
          n.pageName.isNotEmpty &&
          _normalizedText(pageName) == _normalizedText(n.pageName);
      return sameName || overlap >= 2;
    });

    if (existing >= 0) {
      _nodes[existing].visitCount++;
      if (confidence > _nodes[existing].confidence) {
        _nodes[existing].confidence = confidence;
      }
      _currentNodeId = _nodes[existing].nodeId;
      onNodeChange?.call(_currentNodeId!);
      return _nodes[existing];
    }

    final keyTexts = texts.take(10).toList();
    final pageType = _inferPageType(
      keyTexts.isEmpty ? [pageSummary] : keyTexts,
    );
    final resolvedPageName = pageName.trim().isNotEmpty
        ? pageName.trim()
        : _inferPageTypeLabel(pageType);
    final nodeId = _stableNodeId(pageType, resolvedPageName, keyTexts);

    final node = InferredNode(
      nodeId: nodeId,
      pageType: pageType,
      pageName: resolvedPageName,
      keyTexts: keyTexts,
      firstSeen: DateTime.now(),
      confidence: confidence,
    );
    _nodes.add(node);
    _currentNodeId = nodeId;
    onNodeChange?.call(nodeId);
    _log('发现录屏节点: $nodeId ($pageType)');
    return node;
  }

  void _recordNodeObservation(
    InferredNode node,
    String signature,
    List<String> texts,
  ) {
    _recordCanonical('node_located', {
      'node_id': node.nodeId,
      'node_name': node.pageName,
      'page_type': node.pageType,
      'page_signature': signature,
      'confidence': node.confidence,
      'guidance': _lastSuggestedAction,
      'layout_items': texts
          .take(30)
          .map((text) => {'text': text})
          .toList(),
    });

    if (_previousNodeId != null && _previousNodeId != node.nodeId) {
      _recordCanonical('node_transition', {
        'from_node_id': _previousNodeId,
        'to_node_id': node.nodeId,
        'inferred_action': _lastSuggestedAction,
        'after_page_signature': signature,
        'evidence': 'android_page_change',
      });
    }
    _previousNodeId = node.nodeId;
  }

  String _stableNodeId(
    String pageType,
    String pageName,
    List<String> texts,
  ) {
    final app = _normalizedText(_app ?? 'unknown');
    final type = _normalizedText(pageType);
    final name = _normalizedText(pageName);
    final stableTexts = texts
        .map(_normalizedText)
        .where((text) => text.length >= 2)
        .take(5)
        .toList()
      ..sort();
    final identity = type != 'unknown' && type.isNotEmpty
        ? '$type|$name'
        : '$name|${stableTexts.join("|")}';
    return '${app}_${type.isEmpty ? "page" : type}_${_fnv1a(identity)}';
  }

  String _normalizedText(String value) {
    return value
        .toLowerCase()
        .replaceAll(RegExp(r'\d+(?:\.\d+)?'), '')
        .replaceAll(RegExp(r'[^\u4e00-\u9fa5a-z]+'), '');
  }

  String _fnv1a(String value) {
    var hash = 0x811c9dc5;
    for (final unit in value.codeUnits) {
      hash ^= unit;
      hash = (hash * 0x01000193) & 0xffffffff;
    }
    return hash.toRadixString(16).padLeft(8, '0');
  }

  String _inferPageType(List<String> texts) {
    final t = texts.join(' ');
    if (t.contains('订单详情')) return 'order_detail';
    if (t.contains('订单') && (t.contains('全部') || t.contains('待付款'))) {
      return 'order_list';
    }
    if (t.contains('退款') && t.contains('原因')) return 'refund_form';
    if (t.contains('退款成功') || t.contains('退款中')) return 'refund_result';
    if (t.contains('我的') && t.contains('抖音号')) return 'profile';
    if (t.contains('推荐') && t.contains('关注')) return 'home';
    return 'unknown';
  }

  void addAnnotation({
    required String action,
    required String target,
    String targetType = 'text',
    String note = '',
  }) {
    final anno = {
      'timestamp': DateTime.now().millisecondsSinceEpoch,
      'node_id': _currentNodeId,
      'action': action,
      'target': target,
      'target_type': targetType,
      'note': note,
    };
    _annotations.add(anno);
    _recordCanonical('manual_annotation', {
      'annotation_id': 'android_${_annotations.length}',
      'node_id': _currentNodeId,
      'annotation_timing': 'current_or_previous',
      'action_text': action,
      'target_text': target,
      'target_type': targetType,
      'note': note,
    });
    _scheduleCheckpoint();
    _log('人工标注已添加: $action -> $target');
    onStatusChange?.call();
  }

  Map<String, dynamic> generateCandidateFlow() {
    final flowNodes = _nodes
        .map(
          (n) => {
            'node_id': n.nodeId,
            'page_type': n.pageType,
            'key_indicators': n.keyTexts,
            'guidance': {'action': '请在${_inferPageTypeLabel(n.pageType)}上操作'},
            'risks': [],
            'is_start': _nodes.first == n,
            'is_end': _nodes.last == n,
          },
        )
        .toList();

    final edges = <Map<String, String>>[];
    for (var i = 0; i < _nodes.length - 1; i++) {
      edges.add({'from': _nodes[i].nodeId, 'to': _nodes[i + 1].nodeId});
    }

    return {
      'flow_id': '${_app ?? "unknown"}_${_task ?? "task"}_$_sessionId',
      'app': _app ?? 'unknown',
      'task': _task ?? 'unknown',
      'description': '从训练会话生成的候选流程',
      'nodes': flowNodes,
      'edges': edges,
    };
  }

  String _inferPageTypeLabel(String type) {
    switch (type) {
      case 'home':
        return '首页';
      case 'profile':
        return '个人中心';
      case 'order_list':
        return '订单列表';
      case 'order_detail':
        return '订单详情';
      case 'refund_form':
        return '退款申请页';
      case 'refund_result':
        return '退款结果页';
      default:
        return '当前页面';
    }
  }

  Map<String, dynamic> buildSnapshot() {
    return {
      'format_version': 2,
      'session_id': _sessionId,
      'app': _app,
      'task': _task,
      'capture_mode': _captureMode,
      'started_at': _startedAt?.toIso8601String(),
      'ended_at': _endedAt?.toIso8601String(),
      'status': _status.name,
      'upload_state': _uploaded ? 'uploaded' : 'pending',
      'event_count': _events.length,
      'node_count': _nodes.length,
      'annotation_count': _annotations.length,
      'events': _canonicalEvents,
      'raw_observations': _events.map((e) => e.toJson()).toList(),
      'inferred_nodes': _nodes.map((n) => n.toJson()).toList(),
      'annotations': _annotations,
      'candidate_flow': generateCandidateFlow(),
    };
  }

  Future<String> saveToFile() async {
    final dir = await getApplicationDocumentsDirectory();
    final folder = Directory('${dir.path}/training_sessions');
    await folder.create(recursive: true);

    final filename = '${_app ?? "unknown"}_${_task ?? "task"}_$_sessionId.json';
    final file = File('${folder.path}/$filename');

    await file.writeAsString(json.encode(buildSnapshot()), flush: true);
    _log('训练数据已保存: ${file.path}');
    return file.path;
  }

  static Future<List<File>> pendingSessionFiles() async {
    final dir = await getApplicationDocumentsDirectory();
    final folder = Directory('${dir.path}/training_sessions');
    if (!await folder.exists()) return [];
    final files = await folder
        .list()
        .where((entity) => entity is File && entity.path.endsWith('.json'))
        .cast<File>()
        .toList();
    final pending = <File>[];
    for (final file in files) {
      try {
        final data =
            json.decode(await file.readAsString()) as Map<String, dynamic>;
        final events = data['events'];
        if (data['upload_state'] != 'uploaded' &&
            events is List &&
            events.isNotEmpty) {
          pending.add(file);
        }
      } catch (_) {}
    }
    return pending;
  }

  static Future<void> markFileUploaded(
    File file,
    Map<String, dynamic> serverReceipt,
  ) async {
    final data = json.decode(await file.readAsString()) as Map<String, dynamic>;
    data['upload_state'] = 'uploaded';
    data['uploaded_at'] = DateTime.now().toIso8601String();
    data['server_receipt'] = serverReceipt;
    await file.writeAsString(json.encode(data), flush: true);
  }

  void markUploaded() {
    _uploaded = true;
  }

  void _recordCanonical(String eventType, Map<String, dynamic> payload) {
    _eventSequence++;
    _canonicalEvents.add({
      'event_id': '${_sessionId}_$_eventSequence',
      'session_id': _sessionId,
      'event_type': eventType,
      'timestamp': DateTime.now().toIso8601String(),
      'app': _app,
      'task': _task,
      'capture_mode': _captureMode,
      'frame_seq': _eventSequence,
      'payload': payload,
    });
  }

  void _scheduleCheckpoint() {
    _checkpointTimer?.cancel();
    _checkpointTimer = Timer(
      const Duration(milliseconds: 800),
      () => unawaited(saveToFile()),
    );
  }

  void _log(String message) {
    onLog?.call('[${DateTime.now().toString().substring(11, 19)}] $message');
  }

  void reset() {
    _status = TrainSessionStatus.idle;
    _app = null;
    _task = null;
    _sessionId = '';
    _events.clear();
    _nodes.clear();
    _annotations.clear();
    _canonicalEvents.clear();
    _lastSignature = null;
    _currentNodeId = null;
    _previousNodeId = null;
    _lastSuggestedAction = '';
    _eventSequence = 0;
    _checkpointTimer?.cancel();
    onStatusChange?.call();
  }
}
