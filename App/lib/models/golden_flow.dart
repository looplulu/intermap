import 'dart:convert';

/// 节点中的目标元素信息（Android增强版）
class TargetElement {
  final String? text;
  final String? viewId;
  final String? className;
  final String? positionHint;

  const TargetElement({
    this.text,
    this.viewId,
    this.className,
    this.positionHint,
  });

  factory TargetElement.fromJson(Map<String, dynamic> json) {
    return TargetElement(
      text: json['text'] as String?,
      viewId: json['view_id'] as String?,
      className: json['class_name'] as String?,
      positionHint: json['position_hint'] as String?,
    );
  }
}

/// 关键指标（支持新版结构化格式和旧版文本列表格式）
class KeyIndicators {
  final List<String> texts;
  final List<String> viewIds;
  final String? activity;

  const KeyIndicators({
    this.texts = const [],
    this.viewIds = const [],
    this.activity,
  });

  factory KeyIndicators.fromJson(dynamic json) {
    if (json is List) {
      // 旧版格式: ["退款", "订单详情"]
      return KeyIndicators(texts: List<String>.from(json));
    }
    if (json is Map) {
      return KeyIndicators(
        texts: List<String>.from(json['texts'] ?? []),
        viewIds: List<String>.from(json['view_ids'] ?? []),
        activity: json['activity'] as String?,
      );
    }
    return const KeyIndicators();
  }

  List<String> get allTexts => texts;
}

/// 引导信息
class Guidance {
  final String enter;
  final String action;

  const Guidance({this.enter = '', this.action = ''});

  factory Guidance.fromJson(Map<String, dynamic> json) {
    return Guidance(
      enter: json['enter'] as String? ?? '',
      action: json['action'] as String? ?? '',
    );
  }
}

/// 风险提示
class Risk {
  final String? description;
  final String? type;

  const Risk({this.description, this.type});

  factory Risk.fromJson(Map<String, dynamic> json) {
    return Risk(
      description: json['description'] as String?,
      type: json['type'] as String?,
    );
  }
}

/// Golden Flow 中的一个节点
class FlowNode {
  final String nodeId;
  final String pageType;
  final KeyIndicators keyIndicators;
  final Guidance guidance;
  final List<Risk> risks;
  final TargetElement? targetElement;
  final bool isStart;
  final bool isEnd;

  const FlowNode({
    required this.nodeId,
    required this.pageType,
    required this.keyIndicators,
    required this.guidance,
    this.risks = const [],
    this.targetElement,
    this.isStart = false,
    this.isEnd = false,
  });

  factory FlowNode.fromJson(Map<String, dynamic> json) {
    return FlowNode(
      nodeId: json['node_id'] as String,
      pageType: json['page_type'] as String? ?? 'unknown',
      keyIndicators: KeyIndicators.fromJson(json['key_indicators']),
      guidance: Guidance.fromJson(json['guidance'] ?? {}),
      risks: (json['risks'] as List<dynamic>?)
              ?.map((r) => Risk.fromJson(r as Map<String, dynamic>))
              .toList() ??
          [],
      targetElement: json['target_element'] != null
          ? TargetElement.fromJson(
              json['target_element'] as Map<String, dynamic>)
          : null,
      isStart: json['is_start'] as bool? ?? false,
      isEnd: json['is_end'] as bool? ?? false,
    );
  }
}

/// 一条边（节点之间的转换）
class FlowEdge {
  final String from;
  final String to;

  const FlowEdge({required this.from, required this.to});

  factory FlowEdge.fromJson(Map<String, dynamic> json) {
    return FlowEdge(
      from: json['from'] as String,
      to: json['to'] as String,
    );
  }
}

/// 一条完整的 Golden Flow
class GoldenFlow {
  final String flowId;
  final String app;
  final String task;
  final String description;
  final Map<String, FlowNode> nodes;
  final List<String> nodeOrder;
  final List<FlowEdge> edges;

  GoldenFlow({
    required this.flowId,
    required this.app,
    required this.task,
    this.description = '',
    required this.nodes,
    required this.nodeOrder,
    this.edges = const [],
  });

  factory GoldenFlow.fromJson(Map<String, dynamic> json) {
    final nodesList = json['nodes'] as List<dynamic>;
    final nodeMap = <String, FlowNode>{};
    final order = <String>[];
    for (final n in nodesList) {
      final node = FlowNode.fromJson(n as Map<String, dynamic>);
      nodeMap[node.nodeId] = node;
      order.add(node.nodeId);
    }

    return GoldenFlow(
      flowId: json['flow_id'] as String,
      app: json['app'] as String,
      task: json['task'] as String,
      description: json['description'] as String? ?? '',
      nodes: nodeMap,
      nodeOrder: order,
      edges: (json['edges'] as List<dynamic>?)
              ?.map((e) => FlowEdge.fromJson(e as Map<String, dynamic>))
              .toList() ??
          [],
    );
  }

  factory GoldenFlow.fromJsonString(String jsonStr) {
    return GoldenFlow.fromJson(
        json.decode(jsonStr) as Map<String, dynamic>);
  }

  String? get startNode {
    for (final entry in nodes.entries) {
      if (entry.value.isStart) return entry.key;
    }
    return nodeOrder.isNotEmpty ? nodeOrder.first : null;
  }

  List<String> get endNodes {
    return nodes.entries
        .where((e) => e.value.isEnd)
        .map((e) => e.key)
        .toList();
  }

  String? getNextNode(String currentNodeId) {
    final idx = nodeOrder.indexOf(currentNodeId);
    if (idx == -1) return null;
    if (idx + 1 < nodeOrder.length) return nodeOrder[idx + 1];
    return null;
  }

  FlowNode? getNode(String nodeId) => nodes[nodeId];

  bool isEndNode(String nodeId) => endNodes.contains(nodeId);
}