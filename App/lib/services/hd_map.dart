import '../models/golden_flow.dart';

/// 高层交互地图接口
/// 从内置 JSON 加载 Golden Flow，提供节点匹配和引导获取
class HDMap {
  final Map<String, GoldenFlow> _flows = {}; // key: "app_task"

  /// 从 JSON 数据列表加载
  void loadFromJson(List<Map<String, dynamic>> flowsData) {
    for (final data in flowsData) {
      final flow = GoldenFlow.fromJson(data);
      final key = '${flow.app}_${flow.task}';
      _flows[key] = flow;
    }
  }

  /// 从单个 JSON Map 加载
  void addFlow(Map<String, dynamic> data) {
    final flow = GoldenFlow.fromJson(data);
    final key = '${flow.app}_${flow.task}';
    _flows[key] = flow;
  }

  GoldenFlow? getFlow(String app, String task) {
    return _flows['${app}_$task'];
  }

  /// 匹配节点 —— 优先用控件ID匹配，降级到文本匹配
  /// 返回 (nodeId, confidence, nodeData)
  MatchResult matchNode({
    required List<String> texts,
    required List<String> viewIds,
    required String activity,
    required String app,
    required String task,
  }) {
    final flow = getFlow(app, task);
    if (flow == null) return MatchResult.empty();

    final fullText = texts.join(' ').toLowerCase();

    String? bestNodeId;
    double bestScore = 0.0;
    FlowNode? bestNode;

    for (final entry in flow.nodes.entries) {
      final node = entry.value;
      final indicators = node.keyIndicators;

      // 1. 控件ID匹配（高权重，Android新增能力）
      if (indicators.viewIds.isNotEmpty && viewIds.isNotEmpty) {
        final idMatches = indicators.viewIds
            .where((id) => viewIds.any((vid) => vid.contains(id)))
            .length;
        if (idMatches > 0) {
          final idScore = idMatches / indicators.viewIds.length;
          if (idScore > bestScore) {
            bestScore = idScore;
            bestNodeId = entry.key;
            bestNode = node;
          }
          continue; // ID匹配到就跳过文本匹配
        }
      }

      // 2. Activity匹配
      if (indicators.activity != null &&
          indicators.activity!.isNotEmpty &&
          activity.isNotEmpty) {
        if (activity.contains(indicators.activity!) ||
            indicators.activity!.contains(activity)) {
          if (0.8 > bestScore) {
            bestScore = 0.8;
            bestNodeId = entry.key;
            bestNode = node;
          }
          continue;
        }
      }

      // 3. 文本关键词匹配（降级方案，兼容旧数据）
      if (indicators.allTexts.isEmpty) continue;

      final matched = indicators.allTexts
          .where((ind) => fullText.contains(ind.toLowerCase()))
          .length;
      final strongIndicators = indicators.allTexts
          .where((ind) => ind.length >= 3)
          .toList();
      final matchedStrong = strongIndicators
          .where((ind) => fullText.contains(ind.toLowerCase()))
          .length;

      if (matchedStrong == 0) continue;

      double score = matched / indicators.allTexts.length;
      if (strongIndicators.isNotEmpty) {
        score = 0.6 * (matchedStrong / strongIndicators.length) + 0.4 * score;
      }

      if (score > bestScore) {
        bestScore = score;
        bestNodeId = entry.key;
        bestNode = node;
      }
    }

    if (bestNodeId != null && bestScore >= 0.3) {
      return MatchResult(
        nodeId: bestNodeId,
        confidence: bestScore,
        node: bestNode,
      );
    }

    return MatchResult.empty();
  }

  /// 获取引导文本和风险
  (String guidance, List<String> risks) getGuidance(
    String nodeId,
    String app,
    String task,
  ) {
    final flow = getFlow(app, task);
    if (flow == null) return ('未知页面', []);

    final node = flow.getNode(nodeId);
    if (node == null) return ('未知页面', []);

    final riskTexts = node.risks
        .map((r) => r.description ?? '')
        .where((s) => s.isNotEmpty)
        .toList();

    // 优先使用 action，如果为空则用 enter
    final guidance = node.guidance.action.isNotEmpty
        ? node.guidance.action
        : node.guidance.enter;

    return (guidance, riskTexts);
  }

  bool isEndNode(String nodeId, String app, String task) {
    final flow = getFlow(app, task);
    if (flow == null) return false;
    return flow.isEndNode(nodeId);
  }

  List<String> listFlows() => _flows.keys.toList();

  /// 获取所有可用任务（app, task, description）
  List<Map<String, String>> getAvailableTasks() {
    return _flows.entries.map((e) {
      return {
        'app': e.value.app,
        'task': e.value.task,
        'description': e.value.description,
        'key': e.key,
      };
    }).toList();
  }
}

/// 节点匹配结果
class MatchResult {
  final String? nodeId;
  final double confidence;
  final FlowNode? node;

  const MatchResult({this.nodeId, this.confidence = 0.0, this.node});

  factory MatchResult.empty() =>
      const MatchResult(nodeId: null, confidence: 0.0);
}
