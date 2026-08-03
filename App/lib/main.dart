import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:http/http.dart' as http;

import 'models/nav_event.dart';
import 'services/accessibility_manager.dart';
import 'services/hd_map.dart';
import 'services/guidance_style.dart';
import 'services/navigation_session.dart';
import 'services/screen_capture_service.dart';
import 'services/screen_nav_session.dart';
import 'services/tts_service.dart';
import 'services/training_session.dart';
import 'data/douyin_refund_flow.dart';

@pragma('vm:entry-point')
void accessibilityOverlay() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SizedBox.shrink());
}

void main() {
  runApp(
    ChangeNotifierProvider(
      create: (_) => AppViewModel(),
      child: const InterMapApp(),
    ),
  );
}

class InterMapApp extends StatelessWidget {
  const InterMapApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '小路',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF1A73E8),
        useMaterial3: true,
        brightness: Brightness.light,
      ),
      home: const ModeSelectPage(),
    );
  }
}

/// ============================================================
///  ViewModel
/// ============================================================
class AppViewModel extends ChangeNotifier {
  final AccessibilityServiceManager _a11yManager =
      AccessibilityServiceManager();
  final TTSService _tts = TTSService();
  final HDMap _hdMap = HDMap();
  final NavigationSession _navSession = NavigationSession();
  final ScreenNavSession _screenNavSession = ScreenNavSession(
    tts: TTSService(),
  );
  final ScreenCaptureManager _trainingCapture = ScreenCaptureManager();
  final UiTarsClient _trainingApi = UiTarsClient();
  final FrameChangeDetector _trainingFrameDetector = FrameChangeDetector(
    minInterval: const Duration(seconds: 2),
  );
  final TrainingSessionManager _trainManager = TrainingSessionManager();

  /// MethodChannel 用于调用原生功能
  static const _nativeChannel = MethodChannel('com.intermap/app');

  /// 导航模式：screen（默认录屏）或 a11y（无障碍）
  String _navMode = 'screen';
  GuidanceStyle _guidanceStyle = GuidanceStyle.concise;

  bool _a11yGranted = false;
  String _currentGuidance = '';
  List<String> _currentRisks = [];
  String _debugLog = '';
  Timer? _stuckTimer;
  String _trainLog = '';
  String _uploadStatus = '';
  bool _screenTrainingAnalyzing = false;
  String _trainingMode = 'learn';
  String _trainingPassword = '';
  final List<Map<String, String>> _trainingApiHistory = [];

  // 录屏导航状态
  bool _screenNavActive = false;
  bool _screenNavNavigating = false;
  bool _screenNavComplete = false;

  AppViewModel();

  bool get a11yGranted => _a11yGranted;
  String get navMode => _navMode;
  GuidanceStyle get guidanceStyle => _guidanceStyle;
  SessionStatus get sessionStatus => _navMode == 'screen'
      ? (_screenNavComplete
            ? SessionStatus.complete
            : _screenNavNavigating
            ? SessionStatus.navigating
            : _screenNavActive
            ? SessionStatus.active
            : SessionStatus.idle)
      : _navSession.status;
  String get currentGuidance => _currentGuidance;
  List<String> get currentRisks => _currentRisks;
  String get debugLog => _debugLog;
  int get stepCount => _navSession.stepCount;
  TrainSessionStatus get trainStatus => _trainManager.status;
  String get trainLog => _trainLog;
  String get uploadStatus => _uploadStatus;
  int get trainEventCount => _trainManager.eventCount;
  int get trainNodeCount => _trainManager.nodeCount;
  int get trainAnnotationCount => _trainManager.annotationCount;
  String? get trainCurrentNode => _trainManager.currentNodeId;
  List<InferredNode> get trainNodes => _trainManager.nodes;
  HDMap get hdMap => _hdMap;
  NavigationSession get navSession => _navSession;
  TrainingSessionManager get trainManager => _trainManager;

  void setNavMode(String mode) {
    _navMode = mode;
    notifyListeners();
  }

  void setGuidanceStyle(GuidanceStyle style) {
    if (_guidanceStyle == style) return;
    _guidanceStyle = style;
    _navSession.setGuidanceStyle(style);
    _screenNavSession.setGuidanceStyle(style);
    notifyListeners();
  }

  Future<void> init() async {
    _hdMap.addFlow(douyinRefundFlow);
    await _tts.init();
    _screenNavSession.setTts(_tts);
    _navSession.setGuidanceStyle(_guidanceStyle);
    _screenNavSession.setGuidanceStyle(_guidanceStyle);
    _navSession.setDependencies(
      hdMap: _hdMap,
      onGuidance: _onNavGuidance,
      onOverlayUpdate: (g, r) {},
      onComplete: () => notifyListeners(),
      onStatusChange: () => notifyListeners(),
    );
    _screenNavSession.setDependencies(
      hdMap: _hdMap,
      onGuidance: (g, r) {
        _currentGuidance = g;
        _currentRisks = r;
        notifyListeners();
      },
      onDebugLog: (msg) {
        _debugLog = '$msg\n$_debugLog';
        final lines = _debugLog.split('\n');
        if (lines.length > 80) _debugLog = lines.take(80).join('\n');
        notifyListeners();
      },
      onStatusChange: () => notifyListeners(),
      onComplete: () => notifyListeners(),
    );
    _trainManager.onStatusChange = () => notifyListeners();
    _trainManager.onLog = (log) {
      _trainLog = '$log\n$_trainLog';
      final lines = _trainLog.split('\n');
      if (lines.length > 80) _trainLog = lines.take(80).join('\n');
      notifyListeners();
    };
    _trainManager.onNodeChange = (nodeId) => notifyListeners();
    await checkPermissions();
  }

  Future<void> checkPermissions() async {
    _a11yGranted = await _a11yManager.checkPermission();
    notifyListeners();
  }

  Future<void> requestAccessibility() async {
    await _a11yManager.requestPermission();
    await Future.delayed(const Duration(seconds: 1));
    await checkPermissions();
  }

  /// ── 演示模式 ──
  Future<void> startNavigation({
    required String app,
    required String task,
  }) async {
    _currentGuidance = '';
    _currentRisks = [];

    if (_navMode == 'screen') {
      _screenNavActive = true;
      _screenNavNavigating = false;
      _screenNavComplete = false;
      _debugLog = '录屏导航启动中...\n';
      notifyListeners();

      _stuckTimer?.cancel();
      _stuckTimer = Timer.periodic(const Duration(seconds: 1), (_) {
        _screenNavSession.tick();
      });

      final ok = await _screenNavSession.start(app: app, task: task);
      if (ok) {
        _screenNavNavigating = true;
        _debugLog = '录屏导航已启动，正在监听屏幕...\n$_debugLog';
      } else {
        _screenNavActive = false;
        _stuckTimer?.cancel();
        _debugLog = '录屏导航启动失败（权限被拒绝）\n';
      }
    } else {
      // 无障碍模式
      if (!a11yGranted) {
        _tts.speak('请先开启无障碍服务');
        return;
      }
      _navSession.reset();
      _debugLog = '导航已启动，等待无障碍事件...\n';
      _navSession.start(app: app, task: task);
      _stuckTimer?.cancel();
      _stuckTimer = Timer.periodic(
        const Duration(seconds: 1),
        (_) => _navSession.tick(),
      );
      _startA11yListening(navMode: true);
    }
    notifyListeners();
  }

  void stopNavigation() async {
    _stuckTimer?.cancel();
    if (_navMode == 'screen') {
      await _screenNavSession.stop();
      _screenNavComplete = true;
    } else {
      _a11yManager.stopListening();
      _navSession.stop();
    }
    _tts.speak('导航已结束');
    notifyListeners();
  }

  void resetNav() async {
    _stuckTimer?.cancel();
    if (_navMode == 'screen') {
      _screenNavSession.reset();
    } else {
      _a11yManager.stopListening();
      _navSession.reset();
    }
    _screenNavActive = false;
    _screenNavNavigating = false;
    _screenNavComplete = false;
    _currentGuidance = '';
    _currentRisks = [];
    _debugLog = '';
    notifyListeners();
  }

  void _onNavGuidance(String guidance, List<String> risks) {
    _currentGuidance = guidance;
    _currentRisks = risks;
    final spoken = risks.isEmpty ? guidance : '$guidance。注意，${risks.first}';
    _tts.speak(spoken);
    notifyListeners();
  }

  Future<void> testVoice() async {
    final text = _guidanceStyle == GuidanceStyle.concise
        ? '点右下角的我。'
        : '当前是抖音首页，点击右下角的我，就会进入个人中心。';
    await _tts.speak(text);
  }

  /// ── 训练模式 ──
  Future<void> startTraining({
    required String app,
    required String task,
    required String password,
    bool useA11y = false,
    String mode = 'learn',
  }) async {
    final passwordVerified = await _verifyTrainingPassword(password);
    if (!passwordVerified) {
      _uploadStatus = '训练密码不正确';
      notifyListeners();
      return;
    }
    _trainingPassword = password;
    await _retryPendingTrainingUploads(password);

    final normalizedApp = app.trim().isEmpty ? 'douyin' : app.trim();
    final normalizedTask = task.trim().isEmpty
        ? (mode == 'learn' ? 'free_exploration' : 'douyin_goal_feedback')
        : task.trim();

    _trainingMode = mode;
    _trainManager.reset();
    _trainLog = '';
    _uploadStatus = '';
    _trainManager.start(
      app: normalizedApp,
      task: normalizedTask,
      captureMode: useA11y ? 'android_a11y_gui' : 'android_screen',
    );

    if (useA11y) {
      if (!a11yGranted) {
        _trainManager.reset();
        _tts.speak('请先开启无障碍服务');
        return;
      }
    }

    _trainingApiHistory.clear();
    _trainingFrameDetector.reset();
    _screenTrainingAnalyzing = false;
    _trainLog = useA11y
        ? '无障碍 + GUI 联合训练启动中...\n$_trainLog'
        : '录屏训练启动中...\n$_trainLog';
    notifyListeners();

    final granted = await _trainingCapture.requestPermission();
    if (!granted) {
      if (useA11y) _a11yManager.stopListening();
      _trainManager.reset();
      _trainLog = '录屏训练启动失败（权限被拒绝）\n$_trainLog';
      _tts.speak('请先允许录屏权限');
      return;
    }

    if (useA11y) {
      _startA11yListening(navMode: false, moveToBackground: false);
    }

    _tts.speak(
      mode == 'learn' ? '学习已开始，请正常操作抖音。' : '训练已开始，请按你的目标操作，我会记录页面和你的反馈。',
    );
    try {
      await _nativeChannel.invokeMethod('moveToBackground');
    } catch (_) {}
    await Future.delayed(const Duration(milliseconds: 800));
    _trainingCapture.startListening(_onTrainingFrame);
    notifyListeners();
  }

  void _onTrainingFrame(String base64Frame) {
    if (_trainManager.status != TrainSessionStatus.recording) return;
    if (_screenTrainingAnalyzing) return;
    if (!_trainingFrameDetector.shouldAnalyze(base64Frame)) return;

    _screenTrainingAnalyzing = true;
    _analyzeTrainingFrame(base64Frame).whenComplete(() {
      _screenTrainingAnalyzing = false;
    });
  }

  Future<void> _analyzeTrainingFrame(String base64Frame) async {
    final task = _trainingMode == 'learn'
        ? '学习用户在抖音中的自由操作。请识别当前页面、关键文字、可点击目标，以及用户刚刚可能触发的交互。'
        : '用户正在提出目标并通过实际操作训练小路。请识别当前页面、关键文字、下一步建议、以及是否需要人工反馈纠正。';

    final result = await _trainingApi.analyze(
      base64Image: base64Frame,
      task: task,
      includeOcrEvidence: true,
      history: _trainingApiHistory.take(3).toList(),
    );

    if (result == null || result['ok'] != true) {
      _trainLog = '录屏识别失败: ${result?['error'] ?? 'empty result'}\n$_trainLog';
      notifyListeners();
      return;
    }

    final thought = result['thought']?.toString() ?? '';
    final action = result['action']?.toString() ?? '';
    final actionType = result['action_type']?.toString() ?? '';
    final pageName = result['page_name']?.toString() ?? '';
    final confidence = (result['confidence'] as num?)?.toDouble() ?? 0.0;
    final amounts =
        (result['amounts'] as List<dynamic>?)
            ?.map((item) => item.toString())
            .toList() ??
        const <String>[];
    final keyTexts = _extractTrainingTexts(result);
    final summary = thought.isNotEmpty ? thought : action;

    if (summary.isNotEmpty) {
      _trainingApiHistory.insert(0, {'role': 'assistant', 'content': summary});
      if (_trainingApiHistory.length > 6) _trainingApiHistory.removeLast();
    }

    _trainManager.handleScreenObservation(
      pageSummary: summary.isEmpty ? '录屏页面观察' : summary,
      keyTexts: keyTexts,
      action: action,
      actionType: actionType,
      pageName: pageName,
      confidence: confidence,
      amounts: amounts,
    );
  }

  List<String> _extractTrainingTexts(Map<String, dynamic> result) {
    final raw = result['texts'] ?? result['ocr_texts'] ?? result['key_texts'];
    if (raw is List) {
      return raw
          .map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .take(12)
          .toList();
    }

    final thought = result['thought']?.toString() ?? '';
    final action = result['action']?.toString() ?? '';
    return [thought, action]
        .where((item) => item.trim().isNotEmpty)
        .map((item) => item.trim())
        .take(6)
        .toList();
  }

  Future<void> stopTraining() async {
    _a11yManager.stopListening();
    await _trainingCapture.stop();
    _trainingFrameDetector.reset();
    _screenTrainingAnalyzing = false;
    _trainManager.stop();
    await _trainManager.saveToFile();
    if (_trainingPassword.isNotEmpty) {
      await uploadTrainingData();
    }
    notifyListeners();
  }

  void pauseTraining() => _trainManager.pause();
  void resumeTraining() => _trainManager.resume();

  void addAnnotation({
    required String action,
    required String target,
    String targetType = 'text',
    String note = '',
  }) {
    _trainManager.addAnnotation(
      action: action,
      target: target,
      targetType: targetType,
      note: note,
    );
  }

  Future<String> saveTrainingData() async {
    return await _trainManager.saveToFile();
  }

  /// 上传训练数据到服务器
  Future<bool> uploadTrainingData() async {
    _uploadStatus = '上传中...';
    notifyListeners();

    try {
      final file = File(await _trainManager.saveToFile());
      final snapshot =
          json.decode(await file.readAsString()) as Map<String, dynamic>;
      final receipt = await _postTrainingSnapshot(snapshot, _trainingPassword);
      if (receipt == null) return false;

      _trainManager.markUploaded();
      await TrainingSessionManager.markFileUploaded(file, receipt);
      final storedEvents = receipt['stored_events'] ?? 0;
      final storedNodes = receipt['stored_nodes'] ?? 0;
      final storedAnnotations = receipt['stored_annotations'] ?? 0;
      _uploadStatus =
          '上传成功：$storedEvents个事件，$storedNodes个页面，$storedAnnotations条标注';
      notifyListeners();
      return true;
    } catch (e) {
      _uploadStatus = '上传失败: $e';
      notifyListeners();
      return false;
    }
  }

  Future<bool> _verifyTrainingPassword(String password) async {
    if (password.trim().isEmpty) return false;
    try {
      final response = await http
          .post(
            Uri.parse(
              'https://loop-lulu.com/intermap/api/verify-train-password',
            ),
            headers: {'Content-Type': 'application/json'},
            body: json.encode({'password': password}),
          )
          .timeout(const Duration(seconds: 10));
      if (response.statusCode != 200) return false;
      final data = json.decode(response.body) as Map<String, dynamic>;
      return data['verified'] == true;
    } catch (_) {
      _uploadStatus = '暂时无法连接训练服务器';
      notifyListeners();
      return false;
    }
  }

  Future<Map<String, dynamic>?> _postTrainingSnapshot(
    Map<String, dynamic> snapshot,
    String password,
  ) async {
    final payload = {
      'session_id': snapshot['session_id'],
      'event_type': 'session_batch',
      'timestamp': DateTime.now().toIso8601String(),
      'app': snapshot['app'] ?? 'unknown',
      'task': snapshot['task'] ?? 'unknown',
      'capture_mode': snapshot['capture_mode'] ?? 'android_screen',
      'password': password,
      'payload': snapshot,
    };
    final response = await http
        .post(
          Uri.parse('https://loop-lulu.com/intermap/api/events'),
          headers: {'Content-Type': 'application/json'},
          body: json.encode(payload),
        )
        .timeout(const Duration(seconds: 30));
    if (response.statusCode != 200) {
      _uploadStatus = '上传失败(${response.statusCode})';
      notifyListeners();
      return null;
    }
    final receipt = json.decode(response.body) as Map<String, dynamic>;
    if (receipt['ok'] != true) {
      _uploadStatus = '上传失败：${receipt['error'] ?? '服务器未确认'}';
      notifyListeners();
      return null;
    }
    return receipt;
  }

  Future<void> _retryPendingTrainingUploads(String password) async {
    final files = await TrainingSessionManager.pendingSessionFiles();
    for (final file in files) {
      try {
        final snapshot =
            json.decode(await file.readAsString()) as Map<String, dynamic>;
        final receipt = await _postTrainingSnapshot(snapshot, password);
        if (receipt != null) {
          await TrainingSessionManager.markFileUploaded(file, receipt);
        }
      } catch (_) {
        // 保留文件，下次通过密码验证后继续重试。
      }
    }
  }

  void clearUploadStatus() {
    _uploadStatus = '';
    notifyListeners();
  }

  /// ── 共享监听 ──
  void _startA11yListening({
    required bool navMode,
    bool moveToBackground = true,
  }) {
    // 绑定调试日志，显示每个字段的解析详情
    _a11yManager.onDebugLog = (msg) {
      _debugLog = '$msg\n$_debugLog';
      final lines = _debugLog.split('\n');
      if (lines.length > 80) _debugLog = lines.take(80).join('\n');
      notifyListeners();
    };

    _a11yManager.onRawEvent = (event) {
      final time = DateTime.now().toString().substring(11, 19);
      if (event.eventType == -1) {
        _debugLog = '[$time] ⚠ 事件解析失败\n$_debugLog';
      } else {
        final texts = event.windowTexts.take(5).join(', ');
        _debugLog =
            '[$time] ${event.eventTypeLabel} | ${event.packageName} | 文本(${event.windowTexts.length}): $texts\n$_debugLog';
      }
      if (!navMode && (event.isClick || event.isScroll || event.isTextChange)) {
        _trainManager.handleEvent(event);
      }
      final lines = _debugLog.split('\n');
      if (lines.length > 50) _debugLog = lines.take(50).join('\n');
      notifyListeners();
    };
    _a11yManager.onPageEvent = (event) {
      if (navMode) {
        _navSession.handleAccessibilityEvent(event);
      } else if (event.isPageChange) {
        _trainManager.handleEvent(event);
      }
    };
    // 每次都强制重新订阅，确保用最新回调
    _a11yManager.startListening();

    // 延迟回到桌面，让用户操作目标App
    if (moveToBackground) {
      Future.delayed(const Duration(milliseconds: 500), () {
        _nativeChannel.invokeMethod('moveToBackground');
      });
    }
  }

  @override
  void dispose() {
    _stuckTimer?.cancel();
    _a11yManager.dispose();
    _trainingCapture.stop();
    _screenNavSession.reset();
    _tts.dispose();
    super.dispose();
  }
}

/// ============================================================
///  模式选择首页
/// ============================================================
class ModeSelectPage extends StatefulWidget {
  const ModeSelectPage({super.key});

  @override
  State<ModeSelectPage> createState() => _ModeSelectPageState();
}

class _ModeSelectPageState extends State<ModeSelectPage>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AppViewModel>().init();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      context.read<AppViewModel>().checkPermissions();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('小路', style: TextStyle(fontWeight: FontWeight.bold)),
        centerTitle: true,
        elevation: 0,
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const SizedBox(height: 20),
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.06),
                    blurRadius: 18,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              clipBehavior: Clip.antiAlias,
              child: Padding(
                padding: const EdgeInsets.all(10),
                child: Image.asset(
                  'assets/logo.jpg',
                  fit: BoxFit.contain,
                  semanticLabel: '小路',
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              '小路 - 数字世界导航',
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              '选择使用方式',
              style: TextStyle(color: Colors.grey[600], fontSize: 14),
            ),
            const SizedBox(height: 40),
            _ModeCard(
              icon: Icons.screenshot_monitor,
              iconBg: const Color(0xFFE3F2FD),
              iconColor: const Color(0xFF1565C0),
              title: '演示模式',
              subtitle: '通过实时画面识别抖音页面，体验连续语音导航',
              onTap: () {
                context.read<AppViewModel>().setNavMode('screen');
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => const DemoModePage(captureMode: 'screen'),
                  ),
                );
              },
            ),
            const SizedBox(height: 16),
            _ModeCard(
              icon: Icons.accessibility_new,
              iconBg: const Color(0xFFFCE4EC),
              iconColor: const Color(0xFFC62828),
              title: '无障碍',
              subtitle: '无障碍精确记录操作，配合 GUI 进行学习和训练',
              onTap: () {
                context.read<AppViewModel>().setNavMode('a11y');
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => const CaptureModePage(captureMode: 'a11y'),
                  ),
                );
              },
            ),
            const SizedBox(height: 18),
            OutlinedButton.icon(
              onPressed: () => context.read<AppViewModel>().testVoice(),
              icon: const Icon(Icons.volume_up),
              label: const Text('测试语音'),
            ),
            const Spacer(),
            Text(
              '当前优先打磨抖音；其它 App 后续再扩展',
              style: TextStyle(color: Colors.grey[400], fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}

class _ModeCard extends StatelessWidget {
  final IconData icon;
  final Color iconBg;
  final Color iconColor;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  const _ModeCard({
    required this.icon,
    required this.iconBg,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Row(
            children: [
              Container(
                width: 52,
                height: 52,
                decoration: BoxDecoration(
                  color: iconBg,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(icon, color: iconColor, size: 28),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 17,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: TextStyle(color: Colors.grey[600], fontSize: 13),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: Colors.grey),
            ],
          ),
        ),
      ),
    );
  }
}

class CaptureModePage extends StatefulWidget {
  final String captureMode;
  const CaptureModePage({super.key, required this.captureMode});

  @override
  State<CaptureModePage> createState() => _CaptureModePageState();
}

class _CaptureModePageState extends State<CaptureModePage>
    with WidgetsBindingObserver {
  bool get _isA11y => widget.captureMode == 'a11y';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final vm = context.read<AppViewModel>();
      vm.setNavMode(widget.captureMode);
      vm.checkPermissions();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      context.read<AppViewModel>().checkPermissions();
    }
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<AppViewModel>();
    if (_isA11y && !vm.a11yGranted) {
      return const PermissionGuidePage();
    }

    final title = _isA11y ? '无障碍' : '演示模式';
    final subtitle = _isA11y ? '无障碍记录准确操作，GUI 同步理解完整页面' : '用实时画面理解抖音操作';

    return Scaffold(
      appBar: AppBar(title: Text(title), centerTitle: true),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const SizedBox(height: 12),
            Text(
              title,
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(subtitle, style: TextStyle(color: Colors.grey[600])),
            const SizedBox(height: 36),
            _ModeCard(
              icon: Icons.menu_book,
              iconBg: const Color(0xFFFFF3E0),
              iconColor: const Color(0xFFEF6C00),
              title: '我实际操作进行学习',
              subtitle: '自由操作抖音，同时采集准确点击和完整页面画面',
              onTap: () {
                vm.setNavMode(widget.captureMode);
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) =>
                        TrainRecordingPage(mode: 'learn', useA11y: _isA11y),
                  ),
                );
              },
            ),
            const SizedBox(height: 16),
            _ModeCard(
              icon: Icons.edit_note,
              iconBg: const Color(0xFFE8EAF6),
              iconColor: const Color(0xFF3949AB),
              title: '我提出目标进行导航并反馈',
              subtitle: '带目标操作，结合准确点击、GUI 识别和人工反馈',
              onTap: () {
                vm.setNavMode(widget.captureMode);
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) =>
                        TrainRecordingPage(mode: 'train', useA11y: _isA11y),
                  ),
                );
              },
            ),
            const Spacer(),
            OutlinedButton.icon(
              onPressed: () => vm.testVoice(),
              icon: const Icon(Icons.volume_up),
              label: const Text('测试语音'),
            ),
          ],
        ),
      ),
    );
  }
}

/// ============================================================
///  权限引导
/// ============================================================
class PermissionGuidePage extends StatefulWidget {
  const PermissionGuidePage({super.key});

  @override
  State<PermissionGuidePage> createState() => _PermissionGuidePageState();
}

class _PermissionGuidePageState extends State<PermissionGuidePage> {
  @override
  void initState() {
    super.initState();
    // 页面出现后短暂延迟，让用户看到内容再弹出说明
    Future.delayed(const Duration(milliseconds: 600), () {
      if (mounted) _showPermissionDialog();
    });
  }

  void _showPermissionDialog() {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: [
            Icon(
              Icons.accessibility_new,
              color: Theme.of(ctx).colorScheme.primary,
            ),
            const SizedBox(width: 10),
            const Text('需要无障碍权限'),
          ],
        ),
        content: const Text(
          '小路需要开启"无障碍服务"才能监听App界面变化，为你提供实时语音引导。\n\n'
          '点击"去开启"后会跳转到系统设置，找到"小路"并开启右侧开关即可。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('稍后再说'),
          ),
          FilledButton.icon(
            onPressed: () {
              Navigator.pop(ctx);
              context.read<AppViewModel>().requestAccessibility();
            },
            icon: const Icon(Icons.open_in_new, size: 18),
            label: const Text('去开启'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            children: [
              const Spacer(flex: 3),
              // 简洁的等待画面
              Container(
                width: 88,
                height: 88,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primaryContainer,
                  borderRadius: BorderRadius.circular(24),
                ),
                child: Icon(
                  Icons.accessibility_new,
                  size: 48,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
              const SizedBox(height: 20),
              Text(
                '欢迎使用小路',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                '数字世界的导航助手',
                style: TextStyle(color: Colors.grey[500], fontSize: 15),
              ),
              const Spacer(flex: 2),
              // 底部手动按钮（如果弹窗被关了）
              SizedBox(
                width: double.infinity,
                height: 48,
                child: FilledButton.icon(
                  onPressed: () =>
                      context.read<AppViewModel>().requestAccessibility(),
                  icon: const Icon(Icons.open_in_new, size: 18),
                  label: const Text('开启无障碍服务', style: TextStyle(fontSize: 15)),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Android 13+ 用户：如设置中显示"受限制"，需先去应用详情开启该选项',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey[400], fontSize: 11),
              ),
              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }
}

/// ============================================================
///  演示模式 —— 需求输入页
/// ============================================================
class DemoModePage extends StatefulWidget {
  final String captureMode;
  const DemoModePage({super.key, this.captureMode = 'screen'});

  @override
  State<DemoModePage> createState() => _DemoModePageState();
}

class _DemoModePageState extends State<DemoModePage> {
  final _needCtrl = TextEditingController();
  String _parsedTask = '';

  @override
  void dispose() {
    _needCtrl.dispose();
    super.dispose();
  }

  /// 简单需求解析
  void _parseNeed() {
    final text = _needCtrl.text.trim();
    if (text.isEmpty) return;

    final lower = text.toLowerCase();
    String task = '';

    if (lower.contains('退') || lower.contains('refund')) {
      task = 'refund';
    } else if (lower.contains('买') ||
        lower.contains('下单') ||
        lower.contains('order')) {
      task = 'order';
    } else if (lower.contains('搜') || lower.contains('search')) {
      task = 'search';
    } else {
      task = 'refund'; // 默认
    }

    setState(() {
      _parsedTask = task;
    });
  }

  void _startNav(AppViewModel vm) {
    _parseNeed();
    final task = _parsedTask.isEmpty ? 'refund' : _parsedTask;
    vm.setNavMode(widget.captureMode);
    vm.startNavigation(app: 'douyin', task: task);
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<AppViewModel>();

    if (vm.sessionStatus != SessionStatus.idle) {
      return const DemoNavigationPage();
    }

    return Scaffold(
      appBar: AppBar(title: const Text('演示模式'), centerTitle: true),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.captureMode == 'a11y' ? '无障碍导航测试' : '录屏导航测试',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 6),
            Text(
              '当前先专注抖音。告诉小路你的目标，开始后切到抖音操作。',
              style: TextStyle(color: Colors.grey[600], fontSize: 14),
            ),
            const SizedBox(height: 24),

            const Text(
              '引导方式',
              style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: SegmentedButton<GuidanceStyle>(
                segments: GuidanceStyle.values
                    .map(
                      (style) => ButtonSegment<GuidanceStyle>(
                        value: style,
                        label: Text(style.label),
                        icon: Icon(
                          style == GuidanceStyle.concise
                              ? Icons.short_text
                              : Icons.notes,
                        ),
                      ),
                    )
                    .toList(),
                selected: {vm.guidanceStyle},
                showSelectedIcon: false,
                onSelectionChanged: (selection) {
                  vm.setGuidanceStyle(selection.first);
                },
              ),
            ),
            const SizedBox(height: 8),
            Text(
              vm.guidanceStyle.description,
              style: TextStyle(color: Colors.grey[600], fontSize: 12),
            ),
            const SizedBox(height: 24),

            const Text(
              '当前应用',
              style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
            ),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.grey[100],
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.grey[300]!),
              ),
              child: Row(
                children: [
                  Container(
                    width: 34,
                    height: 34,
                    decoration: BoxDecoration(
                      color: Colors.black,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Center(
                      child: Text(
                        '抖',
                        style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      '抖音 / douyin',
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // 需求输入
            const Text(
              '描述你的需求',
              style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _needCtrl,
              decoration: InputDecoration(
                hintText: '例如：我想退货、我要退款、怎么下单',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                prefixIcon: const Icon(Icons.edit_note),
                suffixIcon: _needCtrl.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () => setState(() => _needCtrl.clear()),
                      )
                    : null,
              ),
              maxLines: 3,
              onChanged: (_) => setState(() {}),
              onSubmitted: (_) => _parseNeed(),
            ),
            const SizedBox(height: 12),

            // 解析结果提示
            if (_parsedTask.isNotEmpty)
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: Colors.green.shade50,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.check_circle,
                      color: Colors.green.shade600,
                      size: 18,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '已识别任务: ${_taskLabel(_parsedTask)}',
                      style: TextStyle(
                        color: Colors.green.shade700,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),

            const SizedBox(height: 32),
            SizedBox(
              width: double.infinity,
              height: 52,
              child: FilledButton.icon(
                onPressed: () => _startNav(vm),
                icon: const Icon(Icons.navigation),
                label: const Text('开始导航', style: TextStyle(fontSize: 17)),
              ),
            ),
            const SizedBox(height: 12),
            Center(
              child: Text(
                '开始导航后，请切换到对应App，小路会自动检测并引导',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey[500], fontSize: 12),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _taskLabel(String task) {
    switch (task) {
      case 'refund':
        return '退款/退货';
      case 'order':
        return '下单购物';
      case 'search':
        return '搜索';
      default:
        return task;
    }
  }
}

/// ============================================================
///  演示模式 —— 导航状态页
/// ============================================================
class DemoNavigationPage extends StatefulWidget {
  const DemoNavigationPage({super.key});

  @override
  State<DemoNavigationPage> createState() => _DemoNavigationPageState();
}

class _DemoNavigationPageState extends State<DemoNavigationPage>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // 从后台回来时，如果导航已结束（complete），自动 reset 回输入页
      final vm = context.read<AppViewModel>();
      if (vm.sessionStatus == SessionStatus.complete) {
        vm.resetNav();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<AppViewModel>();
    final statusColor = switch (vm.sessionStatus) {
      SessionStatus.idle => Colors.grey,
      SessionStatus.active => Colors.blue,
      SessionStatus.navigating => Colors.green,
      SessionStatus.complete => Colors.purple,
      SessionStatus.error => Colors.red,
    };

    return Scaffold(
      appBar: AppBar(
        title: const Text('导航中'),
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => vm.resetNav(),
        ),
      ),
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: statusColor.withValues(alpha: 0.1),
              border: Border(
                bottom: BorderSide(color: statusColor.withValues(alpha: 0.3)),
              ),
            ),
            child: Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: statusColor,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  vm.sessionStatus.label,
                  style: TextStyle(
                    color: statusColor,
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
                const Spacer(),
                if (vm.sessionStatus == SessionStatus.navigating &&
                    vm.navMode != 'screen')
                  Text(
                    '步骤 ${vm.stepCount}',
                    style: TextStyle(color: Colors.grey[600], fontSize: 13),
                  ),
              ],
            ),
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (vm.sessionStatus == SessionStatus.complete)
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Colors.green.shade50,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.green.shade200),
                      ),
                      child: const Row(
                        children: [
                          Icon(
                            Icons.check_circle,
                            color: Colors.green,
                            size: 28,
                          ),
                          SizedBox(width: 12),
                          Text(
                            '导航完成！',
                            style: TextStyle(
                              color: Colors.green,
                              fontWeight: FontWeight.bold,
                              fontSize: 18,
                            ),
                          ),
                        ],
                      ),
                    )
                  else
                    Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.primaryContainer,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(
                                Icons.volume_up,
                                color: Theme.of(context).colorScheme.primary,
                                size: 20,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                '语音引导',
                                style: TextStyle(
                                  color: Theme.of(context).colorScheme.primary,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          Text(
                            vm.currentGuidance.isEmpty
                                ? '正在等待页面变化...'
                                : vm.currentGuidance,
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (vm.currentRisks.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    ...vm.currentRisks.map((risk) => _RiskChip(risk: risk)),
                  ],
                  const SizedBox(height: 16),
                  Text(
                    '调试日志',
                    style: TextStyle(
                      color: Colors.grey[600],
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Container(
                    width: double.infinity,
                    constraints: const BoxConstraints(maxHeight: 200),
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: Colors.grey[100],
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: SingleChildScrollView(
                      reverse: true,
                      child: SelectableText(
                        vm.debugLog.isEmpty ? '等待事件...' : vm.debugLog,
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 11,
                          height: 1.5,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              border: Border(top: BorderSide(color: Colors.grey[200]!)),
            ),
            child: Row(
              children: [
                if (vm.sessionStatus == SessionStatus.complete)
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => vm.resetNav(),
                      child: const Text('返回'),
                    ),
                  )
                else
                  Expanded(
                    child: FilledButton(
                      onPressed: () => vm.stopNavigation(),
                      style: FilledButton.styleFrom(
                        backgroundColor: Colors.red.shade400,
                      ),
                      child: const Text('结束导航'),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// ============================================================
///  无障碍测试模块入口
/// ============================================================
class A11yTestPage extends StatefulWidget {
  const A11yTestPage({super.key});

  @override
  State<A11yTestPage> createState() => _A11yTestPageState();
}

class _A11yTestPageState extends State<A11yTestPage>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      context.read<AppViewModel>().checkPermissions();
    }
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<AppViewModel>();

    if (!vm.a11yGranted) {
      return const PermissionGuidePage();
    }

    return Scaffold(
      appBar: AppBar(title: const Text('无障碍测试'), centerTitle: true),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const SizedBox(height: 20),
            Text(
              '无障碍服务已开启',
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text('选择要测试的功能', style: TextStyle(color: Colors.grey[600])),
            const SizedBox(height: 40),
            _ModeCard(
              icon: Icons.navigation,
              iconBg: const Color(0xFFE3F2FD),
              iconColor: const Color(0xFF1565C0),
              title: '导航测试',
              subtitle: '无障碍事件驱动，测试事件捕获与引导',
              onTap: () {
                vm.setNavMode('a11y');
                Navigator.of(
                  context,
                ).push(MaterialPageRoute(builder: (_) => const DemoModePage()));
              },
            ),
            const SizedBox(height: 16),
            _ModeCard(
              icon: Icons.menu_book,
              iconBg: const Color(0xFFFFF3E0),
              iconColor: const Color(0xFFEF6C00),
              title: '学习测试',
              subtitle: '无障碍事件录制，测试学习流程',
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) =>
                        const TrainRecordingPage(mode: 'learn', useA11y: true),
                  ),
                );
              },
            ),
            const SizedBox(height: 16),
            _ModeCard(
              icon: Icons.edit_note,
              iconBg: const Color(0xFFE8EAF6),
              iconColor: const Color(0xFF3949AB),
              title: '训练测试',
              subtitle: '无障碍事件 + 纠正标注，测试训练流程',
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) =>
                        const TrainRecordingPage(mode: 'train', useA11y: true),
                  ),
                );
              },
            ),
            const Spacer(),
            Text(
              '无障碍服务: 已连接',
              style: TextStyle(color: Colors.green[400], fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}

class _RiskChip extends StatelessWidget {
  final String risk;
  const _RiskChip({required this.risk});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: Colors.orange.shade50,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.orange.shade200),
      ),
      child: Row(
        children: [
          const Icon(Icons.warning_amber, color: Colors.orange, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              risk,
              style: const TextStyle(color: Colors.orange, fontSize: 14),
            ),
          ),
        ],
      ),
    );
  }
}

/// ============================================================
///  训练模式入口
/// ============================================================
class TrainModeEntryPage extends StatelessWidget {
  const TrainModeEntryPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('训练模式'), centerTitle: true),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const SizedBox(height: 20),
            Text(
              '选择训练方式',
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              '录制你的操作流程，让小路学会新任务',
              style: TextStyle(color: Colors.grey[600]),
            ),
            const SizedBox(height: 40),
            _ModeCard(
              icon: Icons.menu_book,
              iconBg: const Color(0xFFFFF3E0),
              iconColor: const Color(0xFFEF6C00),
              title: '学习模式',
              subtitle: '正常操作App，系统自动录制并学习交互路径',
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => const TrainRecordingPage(mode: 'learn'),
                ),
              ),
            ),
            const SizedBox(height: 16),
            _ModeCard(
              icon: Icons.edit_note,
              iconBg: const Color(0xFFE8EAF6),
              iconColor: const Color(0xFF3949AB),
              title: '训练模式',
              subtitle: '输入目标，系统导航，你来纠正和标注错误',
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => const TrainRecordingPage(mode: 'train'),
                ),
              ),
            ),
            const Spacer(),
          ],
        ),
      ),
    );
  }
}

/// ============================================================
///  训练录制页面
/// ============================================================
class TrainRecordingPage extends StatefulWidget {
  final String mode;
  final bool useA11y;
  const TrainRecordingPage({
    super.key,
    required this.mode,
    this.useA11y = false,
  });

  @override
  State<TrainRecordingPage> createState() => _TrainRecordingPageState();
}

class _TrainRecordingPageState extends State<TrainRecordingPage> {
  final _appCtrl = TextEditingController();
  final _taskCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _actionCtrl = TextEditingController();
  final _targetCtrl = TextEditingController();
  final _noteCtrl = TextEditingController();
  String _targetType = 'text';
  bool _showAnnotation = false;

  @override
  void initState() {
    super.initState();
    _appCtrl.text = 'douyin';
  }

  @override
  void dispose() {
    _appCtrl.dispose();
    _taskCtrl.dispose();
    _passwordCtrl.dispose();
    _actionCtrl.dispose();
    _targetCtrl.dispose();
    _noteCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final vm = context.watch<AppViewModel>();
    final isRecording = vm.trainStatus == TrainSessionStatus.recording;
    final isPaused = vm.trainStatus == TrainSessionStatus.paused;
    final isIdle = vm.trainStatus == TrainSessionStatus.idle;
    final isCompleted = vm.trainStatus == TrainSessionStatus.completed;

    return Scaffold(
      appBar: AppBar(
        title: Column(
          children: [
            Text(widget.mode == 'learn' ? '学习模式' : '训练模式'),
            Text(
              widget.useA11y ? '无障碍 + GUI 联合采集' : '录屏 GUI 链路',
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w400),
            ),
          ],
        ),
        centerTitle: true,
      ),
      body: Column(
        children: [
          _TrainStatusBar(vm: vm),
          Expanded(
            child: isIdle
                ? _SetupForm(
                    appCtrl: _appCtrl,
                    taskCtrl: _taskCtrl,
                    passwordCtrl: _passwordCtrl,
                    mode: widget.mode,
                    useA11y: widget.useA11y,
                    onStart: () {
                      vm.startTraining(
                        app: _appCtrl.text.trim(),
                        task: _taskCtrl.text.trim(),
                        password: _passwordCtrl.text,
                        useA11y: widget.useA11y,
                        mode: widget.mode,
                      );
                    },
                  )
                : _RecordingBody(
                    vm: vm,
                    showAnnotation: _showAnnotation,
                    onToggleAnnotation: () =>
                        setState(() => _showAnnotation = !_showAnnotation),
                    actionCtrl: _actionCtrl,
                    targetCtrl: _targetCtrl,
                    noteCtrl: _noteCtrl,
                    targetType: _targetType,
                    onTargetTypeChanged: (v) => setState(() => _targetType = v),
                    onSubmitAnnotation: () {
                      if (_actionCtrl.text.trim().isEmpty ||
                          _targetCtrl.text.trim().isEmpty) {
                        return;
                      }
                      vm.addAnnotation(
                        action: _actionCtrl.text.trim(),
                        target: _targetCtrl.text.trim(),
                        targetType: _targetType,
                        note: _noteCtrl.text.trim(),
                      );
                      _actionCtrl.clear();
                      _targetCtrl.clear();
                      _noteCtrl.clear();
                      setState(() => _showAnnotation = false);
                    },
                  ),
          ),
          // 上传状态提示
          if (vm.uploadStatus.isNotEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
              color: vm.uploadStatus.contains('成功')
                  ? Colors.green.shade50
                  : Colors.orange.shade50,
              child: Text(
                vm.uploadStatus,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: vm.uploadStatus.contains('成功')
                      ? Colors.green.shade700
                      : Colors.orange.shade800,
                  fontSize: 13,
                ),
              ),
            ),
          // 完成后的操作栏
          if (isCompleted)
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                border: Border(top: BorderSide(color: Colors.grey[200]!)),
              ),
              child: Column(
                children: [
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: FilledButton.icon(
                      onPressed: () async {
                        final ok = await vm.uploadTrainingData();
                        if (!ok && context.mounted) {
                          // 上传失败，提示本地保存
                          final path = await vm.saveTrainingData();
                          if (!context.mounted) return;
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('已保存到本地: $path')),
                          );
                        }
                      },
                      icon: const Icon(Icons.cloud_upload),
                      label: const Text(
                        '上传到服务器',
                        style: TextStyle(fontSize: 16),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    height: 44,
                    child: OutlinedButton.icon(
                      onPressed: () async {
                        final path = await vm.saveTrainingData();
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(content: Text('已保存到: $path')),
                          );
                        }
                      },
                      icon: const Icon(Icons.save),
                      label: const Text('保存到本地'),
                    ),
                  ),
                ],
              ),
            ),
          // 录制中的控制栏
          if (!isIdle && !isCompleted)
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                border: Border(top: BorderSide(color: Colors.grey[200]!)),
              ),
              child: Row(
                children: [
                  if (isRecording)
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: () => vm.pauseTraining(),
                        icon: const Icon(Icons.pause),
                        label: const Text('暂停录制'),
                      ),
                    )
                  else if (isPaused)
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: () => vm.resumeTraining(),
                        icon: const Icon(Icons.play_arrow),
                        label: const Text('继续录制'),
                      ),
                    )
                  else
                    const Spacer(),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: () => _confirmStop(context, vm),
                      icon: const Icon(Icons.stop),
                      style: FilledButton.styleFrom(
                        backgroundColor: Colors.red.shade400,
                      ),
                      label: const Text('结束'),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  void _confirmStop(BuildContext context, AppViewModel vm) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('结束训练'),
        content: const Text('结束训练后会自动生成候选流程。是否继续？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () async {
              Navigator.pop(context);
              await vm.stopTraining();
              // 自动尝试上传
              final ok = await vm.uploadTrainingData();
              if (!ok && context.mounted) {
                final path = await vm.saveTrainingData();
                if (!context.mounted) return;
                ScaffoldMessenger.of(
                  context,
                ).showSnackBar(SnackBar(content: Text('已自动保存到本地: $path')));
              }
            },
            child: const Text('结束'),
          ),
        ],
      ),
    );
  }
}

class _TrainStatusBar extends StatelessWidget {
  final AppViewModel vm;
  const _TrainStatusBar({required this.vm});

  @override
  Widget build(BuildContext context) {
    final (color, label) = switch (vm.trainStatus) {
      TrainSessionStatus.idle => (Colors.grey, '空闲'),
      TrainSessionStatus.recording => (Colors.green, '录制中'),
      TrainSessionStatus.paused => (Colors.orange, '已暂停'),
      TrainSessionStatus.completed => (Colors.purple, '已完成'),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        border: Border(bottom: BorderSide(color: color.withValues(alpha: 0.3))),
      ),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(color: color, fontWeight: FontWeight.w600),
          ),
          const Spacer(),
          if (vm.trainStatus != TrainSessionStatus.idle) ...[
            _MiniStat(label: '事件', value: '${vm.trainEventCount}'),
            const SizedBox(width: 12),
            _MiniStat(label: '节点', value: '${vm.trainNodeCount}'),
            const SizedBox(width: 12),
            _MiniStat(label: '标注', value: '${vm.trainAnnotationCount}'),
          ],
        ],
      ),
    );
  }
}

class _MiniStat extends StatelessWidget {
  final String label;
  final String value;
  const _MiniStat({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(label, style: TextStyle(color: Colors.grey[600], fontSize: 11)),
        const SizedBox(width: 2),
        Text(
          value,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12),
        ),
      ],
    );
  }
}

class _SetupForm extends StatelessWidget {
  final TextEditingController appCtrl;
  final TextEditingController taskCtrl;
  final TextEditingController passwordCtrl;
  final String mode;
  final bool useA11y;
  final VoidCallback onStart;
  const _SetupForm({
    required this.appCtrl,
    required this.taskCtrl,
    required this.passwordCtrl,
    required this.mode,
    required this.useA11y,
    required this.onStart,
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '设置训练信息',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: appCtrl,
            decoration: const InputDecoration(
              labelText: '目标 App',
              hintText: '默认 douyin，也可填 com.ss.android.ugc.aweme',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: taskCtrl,
            decoration: InputDecoration(
              labelText: mode == 'learn' ? '操作主题（可选）' : '你的目标',
              hintText: mode == 'learn' ? '不填就是自由探索抖音' : '例如：我要找到订单、我要联系客服',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: passwordCtrl,
            obscureText: true,
            enableSuggestions: false,
            autocorrect: false,
            decoration: const InputDecoration(
              labelText: '训练密码',
              hintText: '验证通过后才能写入服务器训练数据',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.lock_outline),
            ),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: FilledButton.icon(
              onPressed: onStart,
              icon: const Icon(Icons.fiber_manual_record, color: Colors.red),
              label: const Text('开始录制', style: TextStyle(fontSize: 16)),
            ),
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.grey[100],
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Text(
              '提示：开始后按系统提示授权，然后切到抖音正常操作。看不准或图标无文字时，回到小路补一条人工标注。',
              style: TextStyle(color: Colors.grey, fontSize: 12),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            useA11y ? '当前采集：准确点击事件 + GUI 页面识别 + 人工标注' : '当前采集：录屏画面识别 + 人工标注',
            style: TextStyle(color: Colors.grey[500], fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _RecordingBody extends StatelessWidget {
  final AppViewModel vm;
  final bool showAnnotation;
  final VoidCallback onToggleAnnotation;
  final TextEditingController actionCtrl;
  final TextEditingController targetCtrl;
  final TextEditingController noteCtrl;
  final String targetType;
  final ValueChanged<String> onTargetTypeChanged;
  final VoidCallback onSubmitAnnotation;

  const _RecordingBody({
    required this.vm,
    required this.showAnnotation,
    required this.onToggleAnnotation,
    required this.actionCtrl,
    required this.targetCtrl,
    required this.noteCtrl,
    required this.targetType,
    required this.onTargetTypeChanged,
    required this.onSubmitAnnotation,
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (vm.trainCurrentNode != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primaryContainer,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '当前节点',
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.primary,
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    vm.trainCurrentNode!,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 15,
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 12),
          if (vm.trainNodes.isNotEmpty) ...[
            const Text(
              '已发现节点',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 6),
            ...vm.trainNodes.map(
              (n) => Container(
                margin: const EdgeInsets.only(bottom: 6),
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: Colors.grey[100],
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.grey[300]!),
                ),
                child: Row(
                  children: [
                    Text(
                      n.nodeId.split('_').last,
                      style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '${n.pageType} · ${n.keyTexts.take(3).join(", ")}',
                        style: TextStyle(color: Colors.grey[600], fontSize: 12),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text(
                      '×${n.visitCount}',
                      style: TextStyle(color: Colors.grey[500], fontSize: 11),
                    ),
                  ],
                ),
              ),
            ),
          ],
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: onToggleAnnotation,
              icon: Icon(showAnnotation ? Icons.close : Icons.edit_note),
              label: Text(showAnnotation ? '关闭标注' : '添加人工标注'),
            ),
          ),
          if (showAnnotation) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.amber.shade50,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.amber.shade200),
              ),
              child: Column(
                children: [
                  TextField(
                    controller: actionCtrl,
                    decoration: const InputDecoration(
                      labelText: '这步怎么做',
                      hintText: '例如：点击右下角"我"',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: targetCtrl,
                    decoration: const InputDecoration(
                      labelText: '目标是什么',
                      hintText: '例如：个人中心入口',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                  ),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    initialValue: targetType,
                    decoration: const InputDecoration(
                      labelText: '目标类型',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                    items: const [
                      DropdownMenuItem(value: 'text', child: Text('文字按钮')),
                      DropdownMenuItem(value: 'icon', child: Text('图标')),
                      DropdownMenuItem(value: 'avatar', child: Text('头像')),
                      DropdownMenuItem(value: 'menu', child: Text('菜单')),
                      DropdownMenuItem(value: 'other', child: Text('其他')),
                    ],
                    onChanged: (v) {
                      if (v != null) onTargetTypeChanged(v);
                    },
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: noteCtrl,
                    decoration: const InputDecoration(
                      labelText: '补充说明',
                      hintText: '这步容易误点哪里、目标长什么样',
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                    maxLines: 2,
                  ),
                  const SizedBox(height: 10),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: onSubmitAnnotation,
                      child: const Text('保存标注'),
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 16),
          const Text(
            '运行日志',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Container(
            width: double.infinity,
            constraints: const BoxConstraints(maxHeight: 200),
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: Colors.grey[100],
              borderRadius: BorderRadius.circular(8),
            ),
            child: SingleChildScrollView(
              reverse: true,
              child: SelectableText(
                vm.trainLog.isEmpty ? '等待事件...' : vm.trainLog,
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 11,
                  height: 1.5,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
