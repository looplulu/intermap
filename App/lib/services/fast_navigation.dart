import 'guidance_style.dart';
import 'hd_map.dart';

class FastNavigationDecision {
  final String pageKey;
  final String pageName;
  final String guidance;
  final List<String> risks;
  final double confidence;

  const FastNavigationDecision({
    required this.pageKey,
    required this.pageName,
    required this.guidance,
    required this.risks,
    required this.confidence,
  });
}

class FastNavigationResolver {
  final HDMap hdMap;

  const FastNavigationResolver(this.hdMap);

  FastNavigationDecision? resolve({
    required List<String> texts,
    required String app,
    required String task,
    required GuidanceStyle style,
  }) {
    final cleanTexts = texts
        .map((text) => text.trim())
        .where((text) => text.isNotEmpty)
        .toList();
    final fullText = cleanTexts.join(' ');

    if (!fullText.contains('推荐') &&
        !fullText.contains('关注') &&
        fullText.contains('抖音')) {
      return const FastNavigationDecision(
        pageKey: 'android_launcher',
        pageName: '手机桌面',
        guidance: '点屏幕上的抖音图标。',
        risks: [],
        confidence: 0.9,
      );
    }

    final match = hdMap.matchNode(
      texts: cleanTexts,
      viewIds: const [],
      activity: '',
      app: app,
      task: task,
    );
    final node = match.node;
    if (node == null || match.nodeId == null || match.confidence < 0.5) {
      return null;
    }

    final guidance = GuidanceFormatter.fromStructured(
      page: node.guidance.enter,
      action: node.guidance.action,
      style: style,
    );
    final risks = node.risks
        .map((risk) => risk.description ?? '')
        .where((risk) => risk.isNotEmpty)
        .toList();
    return FastNavigationDecision(
      pageKey: 'map_${match.nodeId}',
      pageName: node.pageType,
      guidance: guidance,
      risks: risks,
      confidence: match.confidence,
    );
  }
}
