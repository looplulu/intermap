package com.intermap.intermap_app

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import android.util.Base64
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import java.util.Locale

class MainActivity : FlutterActivity() {
    private val APP_CHANNEL = "com.intermap/app"
    private val CAPTURE_EVENT_CHANNEL = "com.intermap/capture_event"
    private val VISION_CHANNEL = "com.intermap/vision"

    private val REQUEST_CODE_SCREEN_CAPTURE = 2001
    private var pendingResult: MethodChannel.Result? = null
    private var captureEventSink: EventChannel.EventSink? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private var nativeTts: TextToSpeech? = null
    private var nativeTtsReady = false
    private val pendingTtsTexts = mutableListOf<Triple<String, Float, Float>>()
    private val textRecognizerDelegate = lazy {
        TextRecognition.getClient(ChineseTextRecognizerOptions.Builder().build())
    }
    private val textRecognizer: TextRecognizer by textRecognizerDelegate

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        // App 通用 MethodChannel
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, APP_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "moveToBackground" -> {
                    moveTaskToBack(true)
                    result.success(null)
                }
                "requestScreenCapture" -> {
                    pendingResult = result
                    requestScreenCapture()
                }
                "stopScreenCapture" -> {
                    stopScreenCapture()
                    result.success(null)
                }
                "speakNative" -> {
                    val text = call.argument<String>("text").orEmpty()
                    val speechRate = (call.argument<Double>("speechRate") ?: 0.5).toFloat()
                    val pitch = (call.argument<Double>("pitch") ?: 1.0).toFloat()
                    result.success(speakNative(text, speechRate, pitch))
                }
                "stopNativeTts" -> {
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
                }
                override fun onCancel(arguments: Any?) {
                    captureEventSink = null
                    ScreenCaptureService.onFrameCaptured = null
                }
            })

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, VISION_CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "recognizeText" -> recognizeText(
                        call.argument<String>("imageBase64").orEmpty(),
                        result
                    )
                    else -> result.notImplemented()
                }
            }
    }

    private fun recognizeText(base64Image: String, result: MethodChannel.Result) {
        if (base64Image.isBlank()) {
            result.error("empty_image", "imageBase64 is required", null)
            return
        }
        val bitmap = try {
            val bytes = Base64.decode(base64Image, Base64.DEFAULT)
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
        } catch (error: Exception) {
            null
        }
        if (bitmap == null) {
            result.error("decode_failed", "Unable to decode screenshot", null)
            return
        }

        val startedAt = SystemClock.elapsedRealtime()
        textRecognizer.process(InputImage.fromBitmap(bitmap, 0))
            .addOnSuccessListener { recognized ->
                val lines = recognized.textBlocks
                    .flatMap { block -> block.lines }
                    .map { line -> line.text.trim() }
                    .filter { text -> text.isNotEmpty() }
                    .distinct()
                    .take(120)
                result.success(
                    mapOf(
                        "ok" to true,
                        "texts" to lines,
                        "duration_ms" to (SystemClock.elapsedRealtime() - startedAt)
                    )
                )
            }
            .addOnFailureListener { error ->
                result.error("ocr_failed", error.message, null)
            }
            .addOnCompleteListener {
                bitmap.recycle()
            }
    }

    private fun requestScreenCapture() {
        val mgr = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        @Suppress("DEPRECATION")
        startActivityForResult(mgr.createScreenCaptureIntent(), REQUEST_CODE_SCREEN_CAPTURE)
    }

    @Deprecated("Use registerForActivityResult")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_CODE_SCREEN_CAPTURE) {
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
                    nativeTts?.language = Locale.SIMPLIFIED_CHINESE
                    selectComfortableChineseVoice()
                    flushPendingTts()
                } else {
                    nativeTtsReady = false
                    pendingTtsTexts.clear()
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
        nativeTts?.setSpeechRate(speechRate)
        nativeTts?.setPitch(pitch)
        nativeTts?.speak(
            text,
            TextToSpeech.QUEUE_FLUSH,
            null,
            "intermap_${System.currentTimeMillis()}"
        )
    }

    override fun onDestroy() {
        if (textRecognizerDelegate.isInitialized()) {
            textRecognizer.close()
        }
        nativeTts?.stop()
        nativeTts?.shutdown()
        nativeTts = null
        super.onDestroy()
    }
}
