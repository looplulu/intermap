package com.intermap.intermap_app

import android.annotation.SuppressLint
import android.app.*
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import android.util.Base64
import android.util.DisplayMetrics
import android.view.WindowManager
import java.io.ByteArrayOutputStream

class ScreenCaptureService : Service() {

    companion object {
        const val CHANNEL_ID = "screen_capture_channel"
        const val NOTIFICATION_ID = 1001
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_DATA = "data"

        /** 截屏回调，通过静态变量让 MainActivity 传递给 EventChannel */
        var onFrameCaptured: ((String) -> Unit)? = null

        private const val MIN_FRAME_INTERVAL_MS = 300L

        @Volatile
        var isRunning = false
            private set
    }

    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private var handler: Handler? = null
    private var lastFrameAtMs = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    @SuppressLint("ForegroundServiceType")
    override fun onCreate() {
        super.onCreate()
        handler = Handler(Looper.getMainLooper())

        // 创建通知渠道（Android 8+）
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "屏幕捕获",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "小路正在捕获屏幕以提供导航引导"
                setShowBadge(false)
            }
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(channel)
        }

        // 启动前台通知
        val notification = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }.apply {
            setContentTitle("小路")
            setContentText("正在为您提供导航引导")
            setSmallIcon(android.R.drawable.ic_menu_compass)
            setOngoing(true)
        }.build()

        startForeground(NOTIFICATION_ID, notification)

        // 请求音频焦点，确保后台 TTS 能正常播放
        requestAudioFocus()
    }

    private var audioManager: AudioManager? = null
    private var focusRequest: AudioFocusRequest? = null

    @SuppressLint("NewApi")
    private fun requestAudioFocus() {
        audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val attrs = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
            focusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
                .setAudioAttributes(attrs)
                .build()
            audioManager?.requestAudioFocus(focusRequest!!)
        } else {
            @Suppress("DEPRECATION")
            audioManager?.requestAudioFocus(
                null, AudioManager.STREAM_MUSIC,
                AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK
            )
        }
    }

    private fun abandonAudioFocus() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && focusRequest != null) {
            audioManager?.abandonAudioFocusRequest(focusRequest!!)
        } else {
            @Suppress("DEPRECATION")
            audioManager?.abandonAudioFocus(null)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED)
            ?: return stopAndReturn()
        val data: Intent = intent.getParcelableExtra(EXTRA_DATA)
            ?: return stopAndReturn()

        try { setupMediaProjection(resultCode, data) }
        catch (e: Exception) {
            TrainingRecorder.captureStopped()
            return stopAndReturn()
        }
        return START_NOT_STICKY
    }

    @SuppressLint("WrongConstant")
    private fun setupMediaProjection(resultCode: Int, data: Intent) {
        val mgr = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        mediaProjection = mgr.getMediaProjection(resultCode, data)

        mediaProjection?.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                cleanup()
            }
        }, handler)

        // 获取屏幕尺寸
        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getRealMetrics(metrics)
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val density = metrics.densityDpi

        // 创建 ImageReader
        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)

        // 创建 VirtualDisplay
        virtualDisplay = mediaProjection?.createVirtualDisplay(
            "InterMapCapture",
            width, height, density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader!!.surface, null, handler
        )

        // 监听图像帧
        imageReader!!.setOnImageAvailableListener({ reader ->
            val image: Image? = reader.acquireLatestImage()
            if (image != null) {
                val now = SystemClock.elapsedRealtime()
                if (now - lastFrameAtMs < MIN_FRAME_INTERVAL_MS) {
                    image.close()
                    return@setOnImageAvailableListener
                }
                lastFrameAtMs = now

                var bitmap: Bitmap? = null
                try {
                    bitmap = imageToBitmap(image, width, height)
                    if (TrainingRecorder.active) {
                        @Suppress("DEPRECATION")
                        val rotation = (getSystemService(Context.WINDOW_SERVICE) as WindowManager).defaultDisplay.rotation
                        TrainingRecorder.frame(bitmap, SystemClock.uptimeMillis(), rotation)
                    } else {
                        val base64 = bitmapToBase64(bitmap, 65)
                        onFrameCaptured?.invoke(base64)
                    }
                } catch (e: Exception) {
                    TrainingRecorder.record("capture_gap", mapOf("reason" to "frame_error", "error" to e.javaClass.simpleName))
                } finally {
                    bitmap?.recycle()
                    image.close()
                }
            }
        }, handler)

        isRunning = true
    }

    private fun imageToBitmap(image: Image, width: Int, height: Int): Bitmap {
        val planes = image.planes
        val buffer = planes[0].buffer
        val pixelStride = planes[0].pixelStride
        val rowStride = planes[0].rowStride
        val rowPadding = rowStride - pixelStride * width

        val bitmap = Bitmap.createBitmap(
            width + rowPadding / pixelStride, height, Bitmap.Config.ARGB_8888
        )
        bitmap.copyPixelsFromBuffer(buffer)
        if (rowPadding == 0) return bitmap

        val cropped = Bitmap.createBitmap(bitmap, 0, 0, width, height)
        bitmap.recycle()
        return cropped
    }

    private fun bitmapToBase64(bitmap: Bitmap, quality: Int): String {
        // 1.0.08 的低延迟基线：缩小一半，减少上传和视觉推理时间。
        val scaledWidth = bitmap.width / 2
        val scaledHeight = bitmap.height / 2
        val scaled = Bitmap.createScaledBitmap(bitmap, scaledWidth, scaledHeight, true)
        return try {
            val outputStream = ByteArrayOutputStream()
            scaled.compress(Bitmap.CompressFormat.JPEG, quality, outputStream)
            Base64.encodeToString(outputStream.toByteArray(), Base64.NO_WRAP)
        } finally {
            scaled.recycle()
        }
    }

    private fun stopAndReturn(): Int {
        cleanup()
        stopSelf()
        return START_NOT_STICKY
    }

    private fun cleanup() {
        TrainingRecorder.captureStopped()
        isRunning = false
        lastFrameAtMs = 0L
        abandonAudioFocus()
        virtualDisplay?.release()
        virtualDisplay = null
        imageReader?.close()
        imageReader = null
        mediaProjection?.stop()
        mediaProjection = null
    }

    override fun onDestroy() {
        cleanup()
        super.onDestroy()
    }
}
