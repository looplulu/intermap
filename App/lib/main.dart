import 'package:flutter/material.dart';
import 'services/consumer_session.dart';

void main() => runApp(const XiaoluApp());

class XiaoluApp extends StatelessWidget {
  const XiaoluApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: '小路',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff287b44)),
      scaffoldBackgroundColor: const Color(0xfff7faf7),
      textTheme: const TextTheme(bodyLarge: TextStyle(fontSize: 19)),
    ),
    home: const TaskHome(),
  );
}

class TaskHome extends StatefulWidget {
  const TaskHome({super.key});
  @override
  State<TaskHome> createState() => _TaskHomeState();
}

class _TaskHomeState extends State<TaskHome> {
  final session = ConsumerSession();
  final input = TextEditingController();
  bool accepted = false;
  bool busyVoice = false;
  String voiceError = '';
  @override
  void initState() {
    super.initState();
    session.addListener(refresh);
    ConsumerSession.bridge.setMethodCallHandler((call) async {
      if (call.method == 'nativeSpeechDone') await session.flushGuidance();
      if (call.method == 'speechUnavailable') {
        voiceError = '手机的朗读服务没有启动，请在系统设置中启用中文文字转语音。';
        refresh();
      }
      if (call.method == 'captureStopped' || call.method == 'hostVisible') {
        if (session.state == TaskState.navigating ||
            session.state == TaskState.confirming ||
            (call.method == 'captureStopped' &&
                session.state == TaskState.authorizing)) {
          await session.pause();
        }
      }
      if (call.method == 'companionAction') {
        final args = Map<String, dynamic>.from(call.arguments as Map);
        switch (args['action']) {
          case 'start':
            input.text = args['goal'] as String? ?? '';
            await begin();
          case 'voice':
            await voice();
          case 'repeat':
            await session.repeat();
          case 'pause':
            session.state == TaskState.paused
                ? await session.resume()
                : await session.pause();
          case 'completed':
            await confirmEnd(true);
          case 'cancelled':
            await confirmEnd(false);
          case 'not_found':
            await session.help('not_found');
          case 'wrong_step':
            await session.help('wrong_step');
        }
      }
    });
    loadSettings();
  }

  Future<void> loadSettings() async {
    try {
      final data = await ConsumerSession.bridge
          .invokeMapMethod<String, dynamic>('loadSettings');
      accepted = data?['accepted'] == true;
      session.consent = data?['consent'] == true;
      session.detailed = data?['detailed'] == true;
      await session.retryFeedback();
      refresh();
    } catch (_) {}
  }

  Future<void> saveSettings() async {
    try {
      await ConsumerSession.bridge.invokeMethod('saveSettings', {
        'accepted': accepted,
        'consent': session.consent,
        'detailed': session.detailed,
      });
    } catch (_) {}
  }

  void refresh() {
    if (mounted) setState(() {});
  }

  Future<void> begin() async {
    if (input.text.trim().isEmpty) return;
    if (!accepted) {
      await ConsumerSession.bridge.invokeMethod('moveToForeground');
      if (!mounted) return;
      final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
          title: const Text('开始使用小路'),
          content: const SingleChildScrollView(
            child: Text(
              '小路需要联网，将你主动共享的画面交给云端模型分析，并用语音告诉你下一步。请勿共享密码、验证码、支付和私人聊天。\n\n你始终自己操作手机，可以随时暂停或停止共享。模型可能判断错误，重要选择请自行核实。\n\n默认不保存连续截图。用于改进的结构化反馈可在设置中单独选择。',
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(c, false),
              child: const Text('暂不使用'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(c, true),
              child: const Text('了解并继续'),
            ),
          ],
        ),
      );
      if (ok != true) return;
      accepted = true;
      if (!mounted) return;
      session.consent =
          await showDialog<bool>(
            context: context,
            builder: (c) => AlertDialog(
              title: const Text('愿意帮助小路改进吗？'),
              content: const Text(
                '同意后，页面类型、设备与系统版本、指导步骤类别、纠错和任务结果会自动上传，用来整理待核实的路线。不保存连续截图或你的原始目标文字。不同意也能使用导航，可随时在设置中更改。',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(c, false),
                  child: const Text('仅使用导航'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(c, true),
                  child: const Text('同意分享'),
                ),
              ],
            ),
          ) ==
          true;
      await saveSettings();
    }
    await session.start(input.text);
  }

  Future<void> voice() async {
    if (busyVoice) return;
    await session.tts.stop();
    if (session.state == TaskState.navigating) await session.pause();
    await ConsumerSession.bridge.invokeMethod('moveToForeground');
    setState(() {
      busyVoice = true;
      voiceError = '';
    });
    try {
      final result = await ConsumerSession.bridge.invokeMethod<String>(
        'recognizeSpeech',
      );
      if (result != null && result.trim().isNotEmpty) input.text = result;
    } catch (_) {
      voiceError = '这台手机暂时无法识别语音，请在下方输入目标。';
    }
    if (mounted) setState(() => busyVoice = false);
  }

  Future<void> confirmEnd(bool done) async {
    if (session.state == TaskState.idle || session.state == TaskState.ended) {
      return;
    }
    await ConsumerSession.bridge.invokeMethod('moveToForeground');
    if (!mounted) return;
    final yes = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(done ? '目标已经完成了吗？' : '结束这次任务？'),
        content: Text(
          done ? '请确认你想做的事情已经完成。如果还没完成，可以继续让小路引导。' : '结束只代表停止导航，不会记录为成功。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: const Text('继续导航'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(c, true),
            child: Text(done ? '确认完成' : '结束任务'),
          ),
        ],
      ),
    );
    if (yes == true) {
      await session.finish(done);
    } else if (session.state == TaskState.paused ||
        session.state == TaskState.confirming) {
      await session.resume();
    }
  }

  Future<void> companion() async {
    final ok = await ConsumerSession.bridge.invokeMethod<bool>('showCompanion');
    if (!mounted) return;
    if (ok != true) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('授权悬浮显示后，请再点一次开启。')));
    }
  }

  void settings() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (c) => StatefulBuilder(
        builder: (c, update) => SafeArea(
          child: SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '设置',
                    style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
                  ),
                  SwitchListTile(
                    title: const Text('详细语音指导'),
                    value: session.detailed,
                    onChanged: (v) {
                      session.detailed = v;
                      saveSettings();
                      update(() {});
                      refresh();
                    },
                  ),
                  SwitchListTile(
                    title: const Text('分享结构化反馈用于改进'),
                    subtitle: const Text('不保存连续截图；记录仍是待验证证据。'),
                    value: session.consent,
                    onChanged: (v) {
                      session.consent = v;
                      saveSettings();
                      update(() {});
                      refresh();
                    },
                  ),
                  const Text('更改分享设置从下一次任务生效。'),
                  ListTile(
                    leading: const Icon(Icons.volume_up_outlined),
                    title: const Text('试听语音'),
                    onTap: () => session.tts.speak('你好，我是小路。你自己操作，我陪你一步一步来。'),
                  ),
                  ListTile(
                    leading: const Icon(Icons.visibility_off_outlined),
                    title: const Text('隐藏悬浮入口'),
                    onTap: () =>
                        ConsumerSession.bridge.invokeMethod('hideCompanion'),
                  ),
                  const Padding(
                    padding: EdgeInsets.only(top: 16),
                    child: Text(
                      '小路 1.1.02 · 联网试用版\n根据你的目标和当前画面提供指导。暂不支持付款、转账及密码验证码输入。',
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    session.removeListener(refresh);
    session.dispose();
    input.dispose();
    ConsumerSession.bridge.setMethodCallHandler(null);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final active = !{TaskState.idle, TaskState.ended}.contains(session.state);
    return Scaffold(
      appBar: AppBar(
        title: const Text('小路'),
        actions: [
          IconButton(
            tooltip: '设置',
            onPressed: settings,
            icon: const Icon(Icons.settings_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Row(
              children: [
                Image.asset('assets/logo.jpg', width: 58, height: 58),
                const SizedBox(width: 16),
                const Expanded(
                  child: Text(
                    '手机上的事，\n一步一步来。',
                    style: TextStyle(fontSize: 27, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 32),
            const Text(
              '你想在手机上做什么？',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: input,
              minLines: 2,
              maxLines: 4,
              maxLength: 500,
              style: const TextStyle(fontSize: 20),
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                hintText: '告诉小路，你想在手机上做什么',
              ),
            ),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: busyVoice ? null : voice,
                    icon: const Icon(Icons.mic_none),
                    label: Text(busyVoice ? '正在听…' : '说出目标'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: session.state == TaskState.authorizing
                        ? null
                        : begin,
                    icon: const Icon(Icons.navigation_outlined),
                    label: Text(active ? '开始新任务' : '开始导航'),
                  ),
                ),
              ],
            ),
            if (voiceError.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(
                  voiceError,
                  style: const TextStyle(color: Colors.red),
                ),
              ),
            const SizedBox(height: 20),
            OutlinedButton.icon(
              onPressed: companion,
              icon: const Icon(Icons.picture_in_picture_alt),
              label: const Text('开启悬浮小路'),
            ),
            if (session.message.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 28),
                child: Text(
                  session.message,
                  style: const TextStyle(
                    fontSize: 18,
                    color: Color(0xff54685a),
                  ),
                ),
              ),
            if (session.pendingFeedbackCount > 0)
              Text('有 ${session.pendingFeedbackCount} 条反馈等待联网补传。'),
            if (session.guidance.isNotEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 20),
                child: Text(
                  session.guidance,
                  style: const TextStyle(fontSize: 24, height: 1.5),
                ),
              ),
            if (active)
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  OutlinedButton.icon(
                    onPressed: session.repeat,
                    icon: const Icon(Icons.volume_up_outlined),
                    label: const Text('重听'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => session.state == TaskState.paused
                        ? session.resume()
                        : session.pause(),
                    icon: Icon(
                      session.state == TaskState.paused
                          ? Icons.play_arrow
                          : Icons.pause,
                    ),
                    label: Text(
                      session.state == TaskState.paused ? '继续' : '暂停',
                    ),
                  ),
                  TextButton(
                    onPressed: () => session.help('not_found'),
                    child: const Text('没有找到'),
                  ),
                  TextButton(
                    onPressed: () => session.help('wrong_step'),
                    child: const Text('这一步不对'),
                  ),
                  FilledButton(
                    onPressed: () => confirmEnd(true),
                    child: const Text('我已完成'),
                  ),
                  TextButton(
                    onPressed: () => confirmEnd(false),
                    child: const Text('结束任务'),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
