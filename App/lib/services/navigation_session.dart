import '../models/accessibility_event.dart';
import '../models/nav_event.dart';
import 'guidance_style.dart';
import 'hd_map.dart';

/// 页面变化检测器
class PageChangeDetector {
  String _lastSignature = '';
  final Duration stabilityThreshold;

  PageChangeDetector({
    this.stabilityThreshold = const Duration(milliseconds: 500),
  });

  /// 判断页面是否变化
  bool checkChange({
    required String textSignature,
    required String? activityName,
  }) {
    if (_lastSignature.isEmpty) {
      _lastSignature = textSignature;
      return true; // 第一次算变化
    }

    // Activity 变化 = 一定是页面切换
    if (activityName != null && activityName.isNotEmpty) {
      // 简单判断：如果签名差异很大就认为切换了
      final sigChanged = textSignature != _lastSignature;
      if (sigChanged) {
        _lastSignature = textSignature;
        return true;
      }
    }

    // 文本签名变化
    if (textSignature != _lastSignature) {
      _lastSignature = textSignature;
      return true;
    }

    return false;
  }

  void reset() {
    _lastSignature = '';
  }
}

/// 引导回调类型
typedef GuidanceCallback = void Function(String guidance, List<String> risks);

/// 导航会话 —— 核心状态机
/// 从 Python NavigationSession 移植，适配 Android 事件驱动模式
class NavigationSession {
  // 常量
  static const double stuckThreshold = 8.0; // 秒
  static const double lostWindow = 30.0; // 秒
  static const int lostCycleCount = 3;
  static const int maxEscalation = 3;
  static const double minConfidence = 0.3;

  // 状态
  SessionStatus _status = SessionStatus.idle;
  String? _app;
  String _task = '';
  String? _currentNode;
  DateTime? _startedAt;

  final List<NavigationStep> _navigationPath = [];
  final List<InteractionEvent> _events = [];
  final List<String> _unknownNodes = [];

  // 引导升级
  final Map<String, int> _guidanceLevels = {};
  DateTime? _nodeEnterTime;
  String _lastGuidanceHash = '';

  // 迷失检测
  final List<(DateTime, String)> _recentNodeHistory = [];

  // 页面检测
  final PageChangeDetector _pageDetector = PageChangeDetector();

  // 依赖
  HDMap? _hdMap;
  GuidanceCallback? _onGuidance;
  GuidanceCallback? _onOverlayUpdate;
  void Function()? _onComplete;
  void Function()? _onStatusChange;

  // 语音去重
  DateTime? _lastSpokenTime;
  String _lastSpokenText = '';
  GuidanceStyle _guidanceStyle = GuidanceStyle.concise;

  String get sessionId =>
      _startedAt?.millisecondsSinceEpoch.toString().substring(0, 8) ??
      'unknown';

  SessionStatus get status => _status;
  String? get currentNode => _currentNode;
  String get task => _task;
  String? get app => _app;
  int get stepCount => _navigationPath.length;
  List<NavigationStep> get path => List.unmodifiable(_navigationPath);

  void setGuidanceStyle(GuidanceStyle style) {
    _guidanceStyle = style;
    _lastSpokenText = '';
    _lastSpokenTime = null;
  }

  void setDependencies({
    required HDMap hdMap,
    GuidanceCallback? onGuidance,
    GuidanceCallback? onOverlayUpdate,
    void Function()? onComplete,
    void Function()? onStatusChange,
  }) {
    _hdMap = hdMap;
    _onGuidance = onGuidance;
    _onOverlayUpdate = onOverlayUpdate;
    _onComplete = onComplete;
    _onStatusChange = onStatusChange;
  }

  /// 开始导航
  void start({required String app, required String task}) {
    if (_status != SessionStatus.idle) {
      throw StateError('无法在 $_status 状态下启动');
    }

    _app = app;
    _task = task;
    _status = SessionStatus.active;
    _startedAt = DateTime.now();
    _pageDetector.reset();

    _events.add(
      InteractionEvent(
        type: EventType.sessionStart,
        data: {'app': app, 'task': task},
      ),
    );

    _onStatusChange?.call();
  }

  /// 处理无障碍事件（Android事件驱动，替代Python的轮询循环）
  void handleAccessibilityEvent(AccessibilityEventData event) {
    if (_status == SessionStatus.complete || _status == SessionStatus.error) {
      return;
    }
    if (_status == SessionStatus.idle) return;
    if (_status == SessionStatus.active) {
      _status = SessionStatus.navigating;
      _onStatusChange?.call();
    }

    // 只处理页面级变化
    if (!event.isPageChange) return;

    // 获取当前窗口的文本信息
    final texts = event.windowTexts;
    if (texts.isEmpty) return;

    // 页面变化检测
    final signature = event.textSignature.isNotEmpty
        ? event.textSignature
        : texts.join('|');
    final changed = _pageDetector.checkChange(
      textSignature: signature,
      activityName: null,
    );
    if (!changed) return;

    // 定位节点
    final viewIds = event.viewId != null ? [event.viewId!] : <String>[];
    final result =
        _hdMap?.matchNode(
          texts: texts,
          viewIds: viewIds,
          activity: '',
          app: _app ?? '',
          task: _task,
        ) ??
        MatchResult.empty();

    if (result.nodeId == null || result.confidence < minConfidence) {
      _handleUnknownPage();
      return;
    }

    final nodeId = result.nodeId!;

    // 迷失检测
    _recordNodeVisit(nodeId);
    if (_isUserLost()) {
      _outputGuidance('你好像来回跳转好几次了，要不要返回首页重新来？', []);
      return;
    }

    // 新节点
    if (nodeId != _currentNode) {
      if (_currentNode != null) {
        _events.add(
          InteractionEvent(
            type: EventType.nodeTransition,
            data: {'from': _currentNode, 'to': nodeId},
          ),
        );
      }
      _guidanceLevels[nodeId] = 1;
      _nodeEnterTime = DateTime.now();
    }

    // 生成引导
    final guidance = _generateGuidance(nodeId);
    final risks = _getRisks(nodeId);
    _outputGuidance(guidance, risks);
    _onOverlayUpdate?.call(guidance, risks);

    // 记录步骤
    _recordStep(nodeId, guidance, result.confidence, risks);
    _currentNode = nodeId;

    // 检查是否完成
    if (_isTaskComplete(nodeId)) {
      _complete();
    }
  }

  /// 卡住检测定时器 —— 由UI层每秒调用
  void tick() {
    if (_status != SessionStatus.navigating || _currentNode == null) return;
    if (_nodeEnterTime == null) return;

    final stuckSeconds = DateTime.now()
        .difference(_nodeEnterTime!)
        .inSeconds
        .toDouble();
    if (stuckSeconds < stuckThreshold) return;

    final level = _guidanceLevels[_currentNode] ?? 1;
    if (level >= maxEscalation) return;

    _escalateGuidance(_currentNode!, level);
  }

  /// 生成引导文本
  String _generateGuidance(String nodeId) {
    if (_hdMap == null) return '稍等，我再看一下这个页面。';
    final node = _hdMap!.getNode(nodeId, _app ?? '', _task);
    if (node == null) return '稍等，我再看一下这个页面。';
    final action = node.guidance.action.isNotEmpty
        ? node.guidance.action
        : node.guidance.enter;
    return GuidanceFormatter.fromStructured(
      page: node.guidance.enter,
      action: action,
      style: _guidanceStyle,
    );
  }

  List<String> _getRisks(String nodeId) {
    if (_hdMap == null) return [];
    final (_, risks) = _hdMap!.getGuidance(nodeId, _app ?? '', _task);
    return risks;
  }

  /// 引导升级
  void _escalateGuidance(String nodeId, int currentLevel) {
    final newLevel = currentLevel + 1;
    _guidanceLevels[nodeId] = newLevel;
    _nodeEnterTime = DateTime.now(); // 重置计时

    final guidance = _generateGuidance(nodeId);

    String escalated;
    if (newLevel == 2) {
      escalated = '$guidance，仔细找一下屏幕上的按钮';
    } else {
      escalated = '$guidance。如果找不到，点左上角返回，回到首页重新来';
    }

    final h = escalated.hashCode.toString();
    if (h == _lastGuidanceHash) return;
    _lastGuidanceHash = h;

    _outputGuidance(escalated, []);
  }

  /// 输出引导
  void _outputGuidance(String guidance, List<String> risks) {
    // 语音去重：70%以上字符重合不重复播报
    if (_isDuplicateSpeech(guidance)) return;
    _lastSpokenText = guidance;
    _lastSpokenTime = DateTime.now();

    _onGuidance?.call(guidance, risks);

    _events.add(
      InteractionEvent(
        type: EventType.navigationGuide,
        data: {'node_id': _currentNode, 'guidance': guidance, 'risks': risks},
      ),
    );
  }

  /// 语音去重判定
  bool _isDuplicateSpeech(String newText) {
    if (_lastSpokenText.isEmpty) return false;
    if (_lastSpokenTime == null) return false;

    // 15秒内不重复
    if (DateTime.now().difference(_lastSpokenTime!).inSeconds < 15) {
      if (_similarity(_lastSpokenText, newText) >= 0.7) {
        return true;
      }
    }
    return false;
  }

  /// 简单字符相似度
  double _similarity(String a, String b) {
    if (a.isEmpty || b.isEmpty) return 0.0;
    final setA = a.runes.toSet();
    final setB = b.runes.toSet();
    final intersection = setA.intersection(setB).length;
    final union = setA.union(setB).length;
    return union == 0 ? 0.0 : intersection / union;
  }

  void _recordStep(
    String nodeId,
    String guidance,
    double confidence,
    List<String> risks,
  ) {
    // 更新上一步时长
    if (_navigationPath.isNotEmpty && _nodeEnterTime != null) {
      final prev = _navigationPath.last;
      prev.durationSeconds = DateTime.now()
          .difference(_nodeEnterTime!)
          .inSeconds
          .toDouble();
    }

    _navigationPath.add(
      NavigationStep(
        nodeId: nodeId,
        pageType: '', // 可从节点数据获取
        guidance: guidance,
        confidence: confidence,
        riskAlerts: risks,
      ),
    );
  }

  void _recordNodeVisit(String nodeId) {
    final now = DateTime.now();
    _recentNodeHistory.add((now, nodeId));
    // 保留窗口内的记录
    _recentNodeHistory.removeWhere(
      (t) => now.difference(t.$1).inSeconds > lostWindow,
    );
  }

  bool _isUserLost() {
    if (_recentNodeHistory.length < 4) return false;
    final nodes = _recentNodeHistory.map((e) => e.$2).toList();
    for (var i = 0; i < nodes.length - 3; i++) {
      if (nodes[i] == nodes[i + 2] &&
          nodes[i + 1] == nodes[i + 3] &&
          nodes[i] != nodes[i + 1]) {
        return true;
      }
    }
    return false;
  }

  void _handleUnknownPage() {
    _unknownNodes.add('unknown_${_unknownNodes.length + 1}');
    _outputGuidance('稍等，我再看一下这个页面。', []);
  }

  bool _isTaskComplete(String nodeId) {
    if (_hdMap != null && _hdMap!.isEndNode(nodeId, _app ?? '', _task)) {
      return true;
    }
    final lower = nodeId.toLowerCase();
    return lower.contains('result') ||
        lower.contains('complete') ||
        lower.contains('success') ||
        lower.contains('finish');
  }

  void _complete() {
    _status = SessionStatus.complete;

    _events.add(
      InteractionEvent(
        type: EventType.sessionComplete,
        data: {'total_steps': _navigationPath.length},
      ),
    );

    _onComplete?.call();
    _onStatusChange?.call();
  }

  /// 手动停止
  void stop() {
    if (_status == SessionStatus.navigating) {
      _complete();
    }
  }

  void reset() {
    _status = SessionStatus.idle;
    _app = null;
    _task = '';
    _currentNode = null;
    _startedAt = null;
    _navigationPath.clear();
    _events.clear();
    _unknownNodes.clear();
    _guidanceLevels.clear();
    _nodeEnterTime = null;
    _lastGuidanceHash = '';
    _recentNodeHistory.clear();
    _lastSpokenText = '';
    _lastSpokenTime = null;
    _pageDetector.reset();
    _onStatusChange?.call();
  }
}
