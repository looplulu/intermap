# 小路 Android 1.1.06

面向中国中老年用户的连续任务导航试用版。用户自己操作，App 看授权画面并给出下一步语音。
本版没有无障碍、人工训练入口或自动点击。接受各App和系统页面中的一般任务，实际覆盖需逐步验收。
同页更新等待当前语音说完，只保留最新待播项；换页且指导改变时才允许打断。
增加常显结束、疑似完成先暂停并确认；同页说完后4秒再提醒一次，黑屏保留共享并引导恢复。
后端导航主路改为DeepSeek Flash；合成界面完整返回约1.1至1.5秒，尚无真机1秒有效指导保证。
1.1.04也可直接使用新后端，无需因模型切换重装。视频布局分离仍未实现。
1.1.06在系统录屏授权前增加图文语音三步提示；微信小店明确购物任务使用有来源的入口约束。

- 入口与系统控制：`lib/main.dart`、`android/app/src/main/kotlin/com/intermap/intermap_app/`
- 状态机与自动反馈：`lib/services/consumer_session.dart`
- 后端：`../digital-interaction-engine/server/consumer_navigation.js`
- 完整接入、数据协议、运维及验收：`../digital-interaction-engine/docs/14-consumer-pilot-1.1.md`

```sh
flutter pub get
flutter analyze
flutter test
JAVA_HOME=/opt/homebrew/Cellar/openjdk@17/17.0.19/libexec/openjdk.jdk/Contents/Home \
  flutter build apk --release --build-name=1.1.06 --build-number=26
```

输出 `build/app/outputs/flutter-apk/app-release.apk`，交付名 `小路1.1.06.apk`。
当前 debug 签名仅用于内部侧载。模型密钥只在服务器；APK 不需训练密码。
语音输入依赖系统服务，女声音质依赖手机 TTS。未做 vivo 真机验收，不保证亚秒识别。

首次使用可单独同意分享结构化反馈，之后自动上传；设置更改从下次任务生效。
连续画面不落训练文件；已同意任务的页面类别、环境、纠错和结果进入服务器待审核记录。
断网反馈先存私有队列，24小时内补传。旧训练材料不会被新版删除，也不由新版继续补传。

历史 `PLAN.md` 和未由新入口引用的训练服务只用于旧版本研究，不代表本版可用功能。
