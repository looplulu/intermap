/// 我们自己的无障碍事件数据结构
/// 从 flutter_accessibility_service 插件事件转换而来
class AccessibilityEventData {
  /// 事件类型ID（Android常量值，不依赖插件枚举）
  final int eventType;
  final String packageName;
  final String? text;
  final String? viewId;
  final bool isClickable;
  final DateTime timestamp;

  /// 从子节点提取的所有文本
  final List<String> windowTexts;

  /// 文本签名（用于页面变化检测）
  final String textSignature;

  AccessibilityEventData({
    required this.eventType,
    required this.packageName,
    this.text,
    this.viewId,
    this.isClickable = false,
    DateTime? timestamp,
    this.windowTexts = const [],
    this.textSignature = '',
  }) : timestamp = timestamp ?? DateTime.now();

  // Android事件类型常量值
  static const int typeViewClicked = 1;
  static const int typeViewLongClicked = 2;
  static const int typeViewSelected = 4;
  static const int typeViewFocused = 8;
  static const int typeViewTextChanged = 16;
  static const int typeWindowStateChanged = 32;
  static const int typeViewScrolled = 4096;
  static const int typeWindowContentChanged = 2048;

  bool get isPageChange =>
      eventType == typeWindowStateChanged ||
      eventType == typeWindowContentChanged;

  bool get isClick =>
      eventType == typeViewClicked || eventType == typeViewLongClicked;

  bool get isScroll => eventType == typeViewScrolled;
  bool get isTextChange => eventType == typeViewTextChanged;

  String get eventTypeLabel {
    switch (eventType) {
      case typeViewClicked:
        return '点击';
      case typeViewLongClicked:
        return '长按';
      case typeViewScrolled:
        return '滚动';
      case typeViewTextChanged:
        return '文本变化';
      case typeWindowStateChanged:
        return '页面切换';
      case typeWindowContentChanged:
        return '内容变化';
      case typeViewSelected:
        return '选择';
      case typeViewFocused:
        return '焦点';
      default:
        return '事件($eventType)';
    }
  }
}
