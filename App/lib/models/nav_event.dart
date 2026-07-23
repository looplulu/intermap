/// 导航会话状态
enum SessionStatus {
  idle,
  active,
  navigating,
  complete,
  error;

  String get label {
    switch (this) {
      case SessionStatus.idle:
        return '空闲';
      case SessionStatus.active:
        return '就绪';
      case SessionStatus.navigating:
        return '导航中';
      case SessionStatus.complete:
        return '已完成';
      case SessionStatus.error:
        return '出错';
    }
  }
}

/// 事件类型
enum EventType {
  sessionStart,
  sessionComplete,
  sessionError,
  pageObserved,
  nodeLocated,
  nodeTransition,
  navigationGuide,
  nodeUnresolved,
}

/// 交互事件
class InteractionEvent {
  final EventType type;
  final DateTime timestamp;
  final Map<String, dynamic> data;

  InteractionEvent({
    required this.type,
    DateTime? timestamp,
    this.data = const {},
  }) : timestamp = timestamp ?? DateTime.now();
}

/// 导航步骤
class NavigationStep {
  final String nodeId;
  final String pageType;
  final String guidance;
  final double confidence;
  final List<String> riskAlerts;
  double durationSeconds;

  NavigationStep({
    required this.nodeId,
    required this.pageType,
    required this.guidance,
    required this.confidence,
    this.riskAlerts = const [],
    this.durationSeconds = 0.0,
  });

  Map<String, dynamic> toJson() => {
        'node_id': nodeId,
        'page_type': pageType,
        'guidance': guidance,
        'confidence': confidence,
        'risk_alerts': riskAlerts,
        'duration_seconds': durationSeconds,
      };
}

/// 完整的交互流程
class InteractionFlow {
  final String task;
  final String app;
  final String sessionId;
  final DateTime startedAt;
  final DateTime completedAt;
  final List<NavigationStep> navigationPath;
  final List<InteractionEvent> events;
  final int totalSteps;
  final List<String> unknownNodes;
  double avgConfidence;
  double totalDuration;

  InteractionFlow({
    required this.task,
    required this.app,
    required this.sessionId,
    required this.startedAt,
    required this.completedAt,
    this.navigationPath = const [],
    this.events = const [],
    this.totalSteps = 0,
    this.unknownNodes = const [],
    this.avgConfidence = 0.0,
    this.totalDuration = 0.0,
  });
}