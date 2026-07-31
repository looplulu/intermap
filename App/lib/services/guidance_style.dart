enum GuidanceStyle {
  concise('简洁', '只告诉你点哪里、点什么'),
  detailed('详细', '说明当前页面和点击后的去向');

  final String label;
  final String description;

  const GuidanceStyle(this.label, this.description);
}

class PageIdentityStabilizer {
  String _stableKey = '';

  void reset() {
    _stableKey = '';
  }

  bool shouldAnnounce(String pageKey) {
    final key = pageKey.trim().isEmpty ? 'unresolved' : pageKey.trim();
    if (_stableKey.isEmpty) {
      _stableKey = key;
      return true;
    }
    if (_samePage(_stableKey, key)) {
      return false;
    }
    _stableKey = key;
    return true;
  }

  bool _samePage(String a, String b) {
    if (a.isEmpty || b.isEmpty) return false;
    if (a == b || a.contains(b) || b.contains(a)) return true;
    return _similarity(a, b) >= 0.58;
  }

  double _similarity(String a, String b) {
    final setA = a.runes.toSet();
    final setB = b.runes.toSet();
    if (setA.isEmpty || setB.isEmpty) return 0;
    return setA.intersection(setB).length / setA.union(setB).length;
  }
}

class GuidanceFormatter {
  static String extractPageName(String text) {
    return _extractField(
          text,
          const ['页面名', '当前页面', '页面'],
          const ['操作', '动作', '建议', '关键文字', '金额'],
        ) ??
        '';
  }

  static String normalizePageKey(String value) {
    return value
        .toLowerCase()
        .replaceAll(RegExp(r'^(?:当前是|这是|当前页面是)\s*'), '')
        .replaceAll(RegExp(r'\d+(?:\.\d+)?'), '')
        .replaceAll(RegExp(r'(?:页面|页)$'), '')
        .replaceAll(RegExp(r'[^\u4e00-\u9fa5a-z]+'), '');
  }

  static String fromModel({
    required String action,
    required String thought,
    required GuidanceStyle style,
  }) {
    final combined = [
      thought,
      action,
    ].where((text) => text.trim().isNotEmpty).join('\n');
    final page = extractPageName(combined);
    final extractedAction =
        _extractField(
          combined,
          const ['操作', '动作', '建议'],
          const ['页面名', '当前页面', '页面', '关键文字', '金额'],
        ) ??
        _cleanAction(action.isNotEmpty ? action : thought);

    return fromStructured(page: page, action: extractedAction, style: style);
  }

  static String fromStructured({
    required String page,
    required String action,
    required GuidanceStyle style,
  }) {
    final cleanAction = _cleanAction(action);
    if (cleanAction.isEmpty) return '稍等，我再看一下这个页面。';
    if (style == GuidanceStyle.concise) return _finish(cleanAction);

    final cleanPage = _cleanPage(page);
    if (cleanPage.isEmpty) return _finish(cleanAction);

    final transition = RegExp(
      r'[，,。；;]\s*(?:(?:然后|点击后|就|即可|可以)\s*)?'
      r'(进入|前往|去到|打开|返回)\s*(.+?)(?:[。！!]|$)',
    ).firstMatch(cleanAction);

    if (transition != null) {
      final instruction = cleanAction.substring(0, transition.start).trim();
      final verb = transition.group(1)!;
      final destination = transition.group(2)!.trim();
      return '当前是$cleanPage，${_stripEnd(instruction)}，就会$verb${_stripEnd(destination)}。';
    }

    return '当前是$cleanPage，${_stripEnd(cleanAction)}。';
  }

  static String? _extractField(
    String text,
    List<String> labels,
    List<String> stopLabels,
  ) {
    if (text.trim().isEmpty) return null;
    final labelPattern = labels.map(RegExp.escape).join('|');
    final stopPattern = stopLabels.map(RegExp.escape).join('|');
    final match = RegExp(
      '(?:$labelPattern)\\s*[:：]\\s*(.+?)(?=\\s*[，,；;]?\\s*(?:$stopPattern)\\s*[:：]|\$)',
      dotAll: true,
    ).firstMatch(text);
    if (match == null) return null;
    final value = match.group(1)?.replaceAll('\n', ' ').trim() ?? '';
    return value.isEmpty ? null : value;
  }

  static String _cleanPage(String text) {
    var value = text.replaceAll('\n', ' ').trim();
    value = value.replaceFirst(RegExp(r'^(?:当前是|这是|当前页面是)\s*'), '');
    value = _stripEnd(value);
    if (value.isEmpty) return '';
    return value.endsWith('页') || value.endsWith('页面') ? value : '$value页面';
  }

  static String _cleanAction(String text) {
    var value = text
        .replaceAll(RegExp(r'[*#`]'), '')
        .replaceAll('\n', ' ')
        .trim();
    value = value.replaceFirst(RegExp(r'^(?:操作|动作|建议)\s*[:：]\s*'), '');
    value = value.replaceFirst(RegExp(r'^(?:请|应该|你需要|下一步)\s*'), '');
    return _stripEnd(value);
  }

  static String _stripEnd(String text) {
    return text.trim().replaceFirst(RegExp(r'[，,。；;！!]+$'), '');
  }

  static String _finish(String text) => '${_stripEnd(text)}。';
}
