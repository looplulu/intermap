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
  final List<String> keyTexts;
  final DateTime firstSeen;
  int visitCount;

  InferredNode({
    required this.nodeId,
    required this.pageType,
    required this.keyTexts,
    required this.firstSeen,
    this.visitCount = 1,
  });

  Map<String, dynamic> toJson() => {
    'node_id': nodeId,
    'page_type': pageType,
    'key_texts': keyTexts,
    'first_seen': firstSeen.toIso8601String(),
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

  String? _lastSignature;
  String? _currentNodeId;
  int _nodeCounter = 0;

  void Function()? onStatusChange;
  void Function(String log)? onLog;
  void Function(String nodeId)? onNodeChange;

  TrainSessionStatus get status => _status;
  String get sessionId => _sessionId;
  String? get app => _app;
  String? get task => _task;
  List<TrainingEvent> get events => List.unmodifiable(_events);
  List<InferredNode> get nodes => List.unmodifiable(_nodes);
  int get eventCount => _events.length;
  int get nodeCount => _nodes.length;
  int get annotationCount => _annotations.length;
  String? get currentNodeId => _currentNodeId;

  void start({required String app, required String task}) {
    _app = app;
    _task = task;
    _sessionId = DateTime.now().millisecondsSinceEpoch.toString();
    _status = TrainSessionStatus.recording;
    _startedAt = DateTime.now();
    _events.clear();
    _nodes.clear();
    _annotations.clear();
    _lastSignature = null;
    _currentNodeId = null;
    _nodeCounter = 0;
    onStatusChange?.call();
    _log('训练开始: $app - $task');
  }

  void stop() {
    _status = TrainSessionStatus.completed;
    _endedAt = DateTime.now();
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

    if (isPageChange && signature.isNotEmpty) {
      _lastSignature = signature;
      _inferNode(event, texts);
    }

    _log('事件: ${event.eventTypeLabel} | ${event.packageName}');
  }

  void handleScreenObservation({
    required String pageSummary,
    required List<String> keyTexts,
    String action = '',
    String actionType = '',
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

    if (isPageChange && signature.isNotEmpty) {
      _lastSignature = signature;
      _inferScreenNode(texts, pageSummary);
    }

    final label = action.isEmpty ? pageSummary : action;
    _log('录屏观察: ${label.isEmpty ? "页面变化" : label}');
  }

  void _inferNode(AccessibilityEventData event, List<String> texts) {
    final existing = _nodes.indexWhere((n) {
      // 简单匹配：关键文本高度重合
      final overlap = n.keyTexts.where((t) => texts.contains(t)).length;
      return overlap >= 3;
    });

    if (existing >= 0) {
      _nodes[existing].visitCount++;
      _currentNodeId = _nodes[existing].nodeId;
      onNodeChange?.call(_currentNodeId!);
      return;
    }

    _nodeCounter++;
    final nodeId = '${_app ?? "unknown"}_${_task ?? "task"}_step$_nodeCounter';
    final keyTexts = texts.take(10).toList();
    final pageType = _inferPageType(keyTexts);

    final node = InferredNode(
      nodeId: nodeId,
      pageType: pageType,
      keyTexts: keyTexts,
      firstSeen: DateTime.now(),
    );
    _nodes.add(node);
    _currentNodeId = nodeId;
    onNodeChange?.call(nodeId);
    _log('发现新节点: $nodeId ($pageType)');
  }

  void _inferScreenNode(List<String> texts, String pageSummary) {
    final existing = _nodes.indexWhere((n) {
      final overlap = n.keyTexts.where((t) => texts.contains(t)).length;
      return overlap >= 2;
    });

    if (existing >= 0) {
      _nodes[existing].visitCount++;
      _currentNodeId = _nodes[existing].nodeId;
      onNodeChange?.call(_currentNodeId!);
      return;
    }

    _nodeCounter++;
    final nodeId = '${_app ?? "unknown"}_${_task ?? "task"}_step$_nodeCounter';
    final keyTexts = texts.take(10).toList();
    final pageType = _inferPageType(
      keyTexts.isEmpty ? [pageSummary] : keyTexts,
    );

    final node = InferredNode(
      nodeId: nodeId,
      pageType: pageType,
      keyTexts: keyTexts,
      firstSeen: DateTime.now(),
    );
    _nodes.add(node);
    _currentNodeId = nodeId;
    onNodeChange?.call(nodeId);
    _log('发现录屏节点: $nodeId ($pageType)');
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

  Future<String> saveToFile() async {
    final dir = await getApplicationDocumentsDirectory();
    final folder = Directory('${dir.path}/training_sessions');
    await folder.create(recursive: true);

    final filename = '${_app ?? "unknown"}_${_task ?? "task"}_$_sessionId.json';
    final file = File('${folder.path}/$filename');

    final data = {
      'session_id': _sessionId,
      'app': _app,
      'task': _task,
      'started_at': _startedAt?.toIso8601String(),
      'ended_at': _endedAt?.toIso8601String(),
      'event_count': _events.length,
      'node_count': _nodes.length,
      'annotation_count': _annotations.length,
      'events': _events.map((e) => e.toJson()).toList(),
      'inferred_nodes': _nodes.map((n) => n.toJson()).toList(),
      'annotations': _annotations,
      'candidate_flow': generateCandidateFlow(),
    };

    await file.writeAsString(json.encode(data));
    _log('训练数据已保存: ${file.path}');
    return file.path;
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
    _lastSignature = null;
    _currentNodeId = null;
    _nodeCounter = 0;
    onStatusChange?.call();
  }
}
