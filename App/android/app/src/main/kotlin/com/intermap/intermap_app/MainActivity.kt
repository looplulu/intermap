package com.intermap.intermap_app

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import android.speech.tts.UtteranceProgressListener
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import java.util.Locale

class MainActivity : FlutterActivity() {
    private val APP_CHANNEL = "com.intermap/app"
    private val CAPTURE_EVENT_CHANNEL = "com.intermap/capture_event"

    private var appBridge: MethodChannel? = null
    private var companion: CompanionOverlay? = null
    private var speechResult: MethodChannel.Result? = null
    private val REQUEST_CODE_SCREEN_CAPTURE = 2001
    private var pendingResult: MethodChannel.Result? = null
    private var captureEventSink: EventChannel.EventSink? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private var nativeTts: TextToSpeech? = null
    private var nativeTtsReady = false
    private var nativeSpeaking = false
    private var nativeUtteranceId: String? = null
    private val pendingTtsTexts = mutableListOf<Triple<String, Float, Float>>()

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        companion = CompanionOverlay(this) { action, goal -> appBridge?.invokeMethod("companionAction", mapOf("action" to action, "goal" to goal)) }
        ScreenCaptureService.onStopped = { mainHandler.post { appBridge?.invokeMethod("captureStopped", null) } }
        ScreenCaptureService.onBlackScreen = { mainHandler.post { appBridge?.invokeMethod("captureBlack", null) } }
        // App 通用 MethodChannel
        appBridge = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, APP_CHANNEL)
        appBridge!!.setMethodCallHandler { call, result ->
            when (call.method) {
                "loadPendingFeedback" -> result.success(getSharedPreferences("consumer", MODE_PRIVATE).getString("pendingFeedback", "[]"))
                "savePendingFeedback" -> {
                    getSharedPreferences("consumer", MODE_PRIVATE).edit().putString("pendingFeedback",call.argument<String>("json") ?: "[]").commit()
                    result.success(null)
                }
                "getEnvironment" -> {
                    val metrics=resources.displayMetrics
                    val douyin=try { packageManager.getPackageInfo("com.ss.android.ugc.aweme",0).versionName } catch (_: Exception) { null }
                    result.success(mapOf("platform" to "android", "manufacturer" to Build.MANUFACTURER,
                        "device_model" to Build.MODEL, "os_version" to Build.VERSION.RELEASE,
                        "sdk" to Build.VERSION.SDK_INT, "width" to metrics.widthPixels,
                        "height" to metrics.heightPixels, "density" to metrics.density,
                        "douyin_version" to douyin, "app_version" to "1.1.06"))
                }
                "moveToForeground" -> { startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)); result.success(null) }
                "loadSettings" -> {
                    val p=getSharedPreferences("consumer", MODE_PRIVATE)
                    result.success(mapOf("accepted" to p.getBoolean("accepted",false), "consent" to p.getBoolean("consent",false), "detailed" to p.getBoolean("detailed",false)))
                }
                "saveSettings" -> {
                    val p=getSharedPreferences("consumer", MODE_PRIVATE).edit()
                    for(k in listOf("accepted","consent","detailed")) p.putBoolean(k,call.argument<Boolean>(k) ?: false)
                    p.apply(); result.success(null)
                }
                "moveToBackground" -> {
                    moveTaskToBack(true)
                    result.success(null)
                }
                "showCompanion" -> {
                    if (!android.provider.Settings.canDrawOverlays(this)) {
                        startActivity(Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION, android.net.Uri.parse("package:$packageName")))
                        result.success(false)
                    } else { companion?.show(); result.success(true) }
                }
                "hideCompanion" -> { companion?.hide(); result.success(null) }
                "updateCompanion" -> { companion?.update(call.argument<String>("text").orEmpty()); result.success(null) }
                "recognizeSpeech" -> {
                    if (speechResult != null) result.error("busy", "正在识别语音", null)
                    else try {
                        speechResult = result
                        startActivityForResult(Intent(android.speech.RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                            putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE_MODEL, android.speech.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                            putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE, "zh-CN")
                        }, 2002)
                    } catch (_: Exception) { speechResult=null; result.error("unavailable", "手机没有可用的语音识别服务，请先使用文字输入", null) }
                }
                "requestScreenCapture" -> {
                    if (pendingResult != null) result.error("busy", "正在等待屏幕共享授权", null)
                    else {
                        startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
                        pendingResult = result
                        mainHandler.postDelayed({ requestScreenCapture() }, 250)
                    }
                }
                "stopScreenCapture" -> {
                    stopScreenCapture()
                    result.success(null)
                }
                "speakNative" -> {
                    if (call.argument<Boolean>("interrupt") == false && (nativeSpeaking || pendingTtsTexts.isNotEmpty())) {
                        result.success("busy")
                        return@setMethodCallHandler
                    }
                    pendingTtsTexts.clear()
                    val text = call.argument<String>("text").orEmpty()
                    val speechRate = (call.argument<Double>("speechRate") ?: 0.5).toFloat()
                    val pitch = (call.argument<Double>("pitch") ?: 1.0).toFloat()
                    result.success(speakNative(text, speechRate, pitch))
                }
                "stopNativeTts" -> {
                    nativeSpeaking = false
                    nativeUtteranceId = null
                    pendingTtsTexts.clear()
                    nativeTts?.stop()
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }

        // 截屏帧 EventChannel
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, CAPTURE_EVENT_CHANNEL)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
                    captureEventSink = events
                    // 将 EventSink 传递给 Service
                    ScreenCaptureService.onFrameCaptured = { base64 ->
                        mainHandler.post {
                            try {
                                events.success(base64)
                            } catch (_: Exception) {}
                        }
                    }
                    ScreenCaptureService.latestFrame?.let { events.success(it) }
                }
                override fun onCancel(arguments: Any?) {
                    captureEventSink = null
                    ScreenCaptureService.onFrameCaptured = null
                }
            })

    }

    private fun requestScreenCapture() {
        speakNative("接下来会出现系统共享窗口。需要切换应用时，请选共享整个屏幕，再点继续。如果出现共享保护，按需要允许目标应用的内容，最后点开始。",0.92f,1.0f)
        android.app.AlertDialog.Builder(this)
            .setTitle("接下来这样允许共享")
            .setMessage("1. 系统弹窗中，先确认共享范围，再点“继续”或“立即开始”。需要跨App导航时选“共享整个屏幕”；只共享单个App时，切换到其他App后可能看不到画面。\n\n2. 如果出现“屏幕共享保护”：愿意共享微信内容时，请检查“隐私应用保护”。开启会隐藏微信，关闭才允许共享；通知、通话等保护不用关闭。若本来已关闭，不用再点。\n\n3. 最后点“开始”。其他品牌请按实际界面操作，没有同名开关时不要乱关权限。\n\n共享时小路会把画面交给云端分析；请避开密码、验证码和私人聊天。")
            .setPositiveButton("开始授权") { _,_ -> launchCapturePermission() }
            .setNegativeButton("取消") { _,_ -> pendingResult?.success(false); pendingResult=null; nativeTts?.stop(); pendingTtsTexts.clear() }
            .setOnCancelListener { pendingResult?.success(false); pendingResult=null; nativeTts?.stop(); pendingTtsTexts.clear() }
            .show()
    }

    private fun launchCapturePermission() {
        val mgr = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        @Suppress("DEPRECATION")
        val permission = if (Build.VERSION.SDK_INT >= 34) {
            mgr.createScreenCaptureIntent(android.media.projection.MediaProjectionConfig.createConfigForDefaultDisplay())
        } else mgr.createScreenCaptureIntent()
        startActivityForResult(permission, REQUEST_CODE_SCREEN_CAPTURE)
    }

    @Deprecated("Use registerForActivityResult")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == 2002) {
            speechResult?.success(if (resultCode == Activity.RESULT_OK) data?.getStringArrayListExtra(android.speech.RecognizerIntent.EXTRA_RESULTS)?.firstOrNull() else null)
            speechResult=null
            return
        }
        if (requestCode == REQUEST_CODE_SCREEN_CAPTURE) {
            pendingTtsTexts.clear(); nativeUtteranceId=null; nativeSpeaking=false; nativeTts?.stop()
            if (resultCode == Activity.RESULT_OK && data != null) {
                // 启动截屏 Service
                val serviceIntent = Intent(this, ScreenCaptureService::class.java).apply {
                    putExtra(ScreenCaptureService.EXTRA_RESULT_CODE, resultCode)
                    putExtra(ScreenCaptureService.EXTRA_DATA, data)
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(serviceIntent)
                } else {
                    @Suppress("DEPRECATION")
                    startService(serviceIntent)
                }
                pendingResult?.success(true)
            } else {
                pendingResult?.success(false)
            }
            pendingResult = null
        }
    }

    private fun stopScreenCapture() {
        ScreenCaptureService.onFrameCaptured = null
        captureEventSink?.endOfStream()
        captureEventSink = null
        stopService(Intent(this, ScreenCaptureService::class.java))
    }

    private fun speakNative(text: String, speechRate: Float, pitch: Float): Boolean {
        if (text.isBlank()) return false
        val utterance = Triple(text, speechRate.coerceIn(0.1f, 1.0f), pitch.coerceIn(0.5f, 2.0f))
        if (nativeTts == null) {
            pendingTtsTexts.add(utterance)
            nativeTts = TextToSpeech(applicationContext) { status ->
                if (status == TextToSpeech.SUCCESS) {
                    nativeTtsReady = true
                    nativeTts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                        override fun onStart(id: String?) {}
                        override fun onDone(id: String?) { speechFinished(id) }
                        override fun onError(id: String?) { speechFinished(id) }
                        override fun onStop(id: String?, interrupted: Boolean) { speechFinished(id) }
                    })
                    nativeTts?.language = Locale.SIMPLIFIED_CHINESE
                    selectComfortableChineseVoice()
                    flushPendingTts()
                } else {
                    nativeTtsReady = false
                    pendingTtsTexts.clear()
                    appBridge?.invokeMethod("speechUnavailable", null)
                }
            }
            return true
        }
        if (!nativeTtsReady) {
            pendingTtsTexts.add(utterance)
            return true
        }
        speakNow(utterance)
        return true
    }

    private fun selectComfortableChineseVoice() {
        val tts = nativeTts ?: return
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) return

        val zhVoices = tts.voices
            ?.filter { voice ->
                val locale = voice.locale
                locale.language == Locale.CHINESE.language &&
                    (locale.country.isBlank() || locale.country == Locale.CHINA.country)
            }
            .orEmpty()
        if (zhVoices.isEmpty()) return

        val preferred = zhVoices.firstOrNull { voice ->
            val name = voice.name.lowercase(Locale.ROOT)
            name.contains("female") ||
                name.contains("xiaoxiao") ||
                name.contains("xiaoyi") ||
                name.contains("xiaobei") ||
                name.contains("xiaoni")
        } ?: zhVoices
            .sortedWith(
                compareBy<Voice> { it.isNetworkConnectionRequired }
                    .thenByDescending { it.quality }
                    .thenBy { it.latency }
            )
            .firstOrNull()

        if (preferred != null) {
            tts.voice = preferred
        }
    }

    private fun flushPendingTts() {
        val texts = pendingTtsTexts.toList()
        pendingTtsTexts.clear()
        texts.forEach { speakNow(it) }
    }

    private fun speakNow(utterance: Triple<String, Float, Float>) {
        val (text, speechRate, pitch) = utterance
        val id = "intermap_${System.nanoTime()}"
        nativeUtteranceId = id
        nativeSpeaking = true
        nativeTts?.setSpeechRate(speechRate)
        nativeTts?.setPitch(pitch)
        val result = nativeTts?.speak(
            text,
            TextToSpeech.QUEUE_FLUSH,
            null,
            id
        )
        if (result == TextToSpeech.ERROR) speechFinished(id)
    }

    private fun speechFinished(id: String?) {
        mainHandler.post {
            if (id != null && id == nativeUtteranceId) {
                nativeSpeaking = false
                nativeUtteranceId = null
                appBridge?.invokeMethod("nativeSpeechDone", null)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        appBridge?.invokeMethod("hostVisible", null)
    }

    override fun onDestroy() {
        companion?.hide()
        ScreenCaptureService.onStopped = null
        ScreenCaptureService.onBlackScreen = null
        speechResult?.success(null)
        speechResult = null
        nativeTts?.stop()
        nativeTts?.shutdown()
        nativeTts = null
        super.onDestroy()
    }
}
