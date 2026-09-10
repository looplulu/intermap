package com.intermap.intermap_app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/** Native evidence capture is independent of Flutter/network inference. */
object TrainingRecorder {
    private val worker = HandlerThread("training-evidence").apply { start() }
    private val handler = Handler(worker.looper)
    private val frameBusy = AtomicBoolean(false)
    @Volatile var active = false
        private set
    @Volatile var paused = false
        private set
    @Volatile var selectedPackage = ""
        private set
    @Volatile var foregroundPackage = ""
    @Volatile var maskedBounds: List<Rect> = emptyList()
    @Volatile var privacyUnknown = true
    @Volatile private var folder: File? = null
    @Volatile private var session = ""
    @Volatile private var count = 0
    @Volatile private var frameCount = 0
    @Volatile private var interactionCount = 0
    @Volatile private var lastActionId: String? = null
    @Volatile private var lastActionLabel = ""
    @Volatile private var bytes = 0L
    @Volatile private var failure = ""
    private var sequence = 0
    private var lastBlockedReason = ""
    private var droppedFrames = 0
    private var lastFrameTime = 0L
    private var lastFrameHash = ""
    private var previousFrameId: String? = null
    private var initialRotation: Int? = null

    fun start(context: Context, metadata: Map<String, Any?>, done: (Map<String, Any?>) -> Unit) {
        handler.post {
            try {
            if (active) { done(status()); return@post }
            session = "android_${UUID.randomUUID()}"
            folder = File(context.filesDir, "training_v3/$session").apply { mkdirs() }
            File(folder, "frames").mkdirs()
            sequence = 0; count = 0; frameCount = 0; interactionCount = 0; bytes = 0
            lastActionId = null; lastActionLabel = ""; failure = ""; lastBlockedReason = ""
            droppedFrames = 0; lastFrameTime = 0; lastFrameHash = ""; previousFrameId = null
            initialRotation = null
            selectedPackage = metadata["package_name"].toString()
            foregroundPackage = ""; privacyUnknown = true; maskedBounds = emptyList()
            paused = false
            val metrics = context.resources.displayMetrics
            val meta = metadata + mapOf(
                "schema_version" to 3, "session_id" to session,
                "source" to "android_a11y_gui", "review_status" to "pending_review",
                "manufacturer" to Build.MANUFACTURER, "model" to Build.MODEL,
                "android_version" to Build.VERSION.RELEASE, "sdk" to Build.VERSION.SDK_INT,
                "density" to metrics.density, "font_scale" to context.resources.configuration.fontScale,
                "app_version" to "1.0.18", "started_at_ms" to System.currentTimeMillis(),
                "position_capability" to "accessibility_source_bounds_not_touch_point",
                "capture_policy" to "selected_app_sampled_frames_300ms_editable_masked"
            )
            atomicJson(File(folder, "metadata.json"), meta)
            active = true
            append("session_start", meta)
            done(status())
            } catch (error: Exception) {
                active = false; failure = "无法创建采集文件: ${error.javaClass.simpleName}"
                done(status())
            }
        }
    }

    fun event(payload: Map<String, Any?>) {
        if (!active || paused) return
        val id = session
        handler.post {
            if (!active || id != session || paused) return@post
            val type = payload["event_type"] as? Int ?: 0
            val record = append("accessibility", payload)
            if (type == 1 || type == 2 || type == 4096 || type == 16) {
                interactionCount++
                lastActionId = record
                val source = payload["source"] as? Map<*, *>
                lastActionLabel = (source?.get("text") ?: source?.get("description")
                    ?: source?.get("view_id") ?: "无文字目标").toString()
            }
        }
    }

    fun frame(bitmap: Bitmap, time: Long, rotation: Int) {
        if (!active || paused) return
        if (initialRotation != null && initialRotation != rotation) {
            failure = "屏幕方向已变化，请结束本次采集并重新开始"; paused = true
            record("capture_gap", mapOf("reason" to "rotation_requires_restart", "uptime_ms" to time))
            return
        }
        initialRotation = rotation
        val reason = when {
            !TrainingAccessibilityService.connected -> "accessibility_disconnected"
            foregroundPackage != selectedPackage -> "outside_selected_app"
            privacyUnknown -> "window_structure_unavailable"
            else -> ""
        }
        if (reason.isNotEmpty()) {
            if (reason != lastBlockedReason) {
                lastBlockedReason = reason
                record("capture_gap", mapOf("reason" to reason, "uptime_ms" to time))
            }
            return
        }
        if (lastBlockedReason.isNotEmpty()) {
            lastBlockedReason = ""
            record("capture_resumed", mapOf("uptime_ms" to time))
        }
        if (!frameBusy.compareAndSet(false, true)) { droppedFrames++; return }
        val id = session
        val masks = maskedBounds.map { Rect(it) }
        val copy = bitmap.copy(Bitmap.Config.ARGB_8888, true)
        handler.post {
            try {
                if (!active || paused || id != session) return@post
                val target = folder ?: return@post
                if (target.usableSpace < 300L * 1024 * 1024) {
                    failure = "手机剩余空间不足，采集已暂停"; paused = true
                    append("capture_gap", mapOf("reason" to "low_disk_space")); return@post
                }
                val canvas = Canvas(copy)
                val paint = Paint().apply { color = Color.LTGRAY }
                masks.forEach { canvas.drawRect(it, paint) }
                val scale = minOf(1.0, 1600.0 / maxOf(copy.width, copy.height))
                val scaled = Bitmap.createScaledBitmap(copy, (copy.width * scale).toInt(), (copy.height * scale).toInt(), true)
                val output = java.io.ByteArrayOutputStream()
                scaled.compress(Bitmap.CompressFormat.JPEG, 88, output)
                val data = output.toByteArray()
                val hash = MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) }
                // Identical pixels are referenced, not stored repeatedly. Each sample still has a timestamp.
                val asset = if (hash == lastFrameHash) previousFrameId!! else "f_${sequence + 1}.jpg"
                if (hash != lastFrameHash) {
                    FileOutputStream(File(target, "frames/$asset")).use { it.write(data); it.fd.sync() }
                    bytes += data.size
                }
                val frame = mapOf(
                    "uptime_ms" to time, "asset" to asset, "sha256" to hash,
                    "screen_width" to copy.width, "screen_height" to copy.height,
                    "image_width" to scaled.width, "image_height" to scaled.height,
                    "rotation" to rotation, "package_name" to selectedPackage,
                    "masked_regions" to masks.map { bounds(it) },
                    "sample_interval_ms" to if (lastFrameTime == 0L) 0 else time - lastFrameTime,
                    "backpressure_drops" to droppedFrames
                )
                if (scaled !== copy) scaled.recycle()
                append("frame", frame)
                frameCount++; droppedFrames = 0; lastFrameTime = time
                lastFrameHash = hash; previousFrameId = asset
            } catch (e: Exception) {
                failure = "画面保存失败: ${e.javaClass.simpleName}"; paused = true
            } finally { copy.recycle(); frameBusy.set(false) }
        }
    }

    fun record(kind: String, payload: Map<String, Any?>) {
        if (!active) return
        val id = session
        handler.post { if (active && id == session) append(kind, payload) }
    }

    fun annotation(payload: Map<String, Any?>, done: (Map<String, Any?>) -> Unit) {
        handler.post {
            if (active) append("annotation", payload + mapOf("action_id" to lastActionId,
                "binding" to "last_observed_interaction", "target_label" to lastActionLabel))
            done(status())
        }
    }

    fun setPaused(value: Boolean) {
        handler.post {
            if (!value && failure.isNotEmpty()) return@post
            paused = value
            if (active) append(if (value) "pause" else "resume", emptyMap())
        }
    }

    fun captureStopped() {
        if (!active) return
        failure = "屏幕采集已停止，请结束本次采集并重新授权"
        paused = true
        record("capture_gap", mapOf("reason" to "screen_capture_stopped"))
    }

    fun stop(done: (Map<String, Any?>) -> Unit) {
        handler.post {
            if (active) {
                append("session_end", mapOf("frame_count" to frameCount, "interaction_count" to interactionCount))
                atomicJson(File(folder, "end.json"), mapOf("total_records" to count, "ended_at_ms" to System.currentTimeMillis()))
                active = false
            }
            done(status())
        }
    }

    fun status(): Map<String, Any?> = mapOf(
        "active" to active, "paused" to paused, "session_id" to session,
        "directory" to folder?.absolutePath, "records" to count, "frames" to frameCount,
        "interactions" to interactionCount, "bytes" to bytes, "error" to failure,
        "last_action_id" to lastActionId, "last_action_label" to lastActionLabel,
        "capture_state" to if (paused) "paused" else lastBlockedReason.ifEmpty { "capturing" },
        "accessibility_connected" to TrainingAccessibilityService.connected
    )

    private fun append(kind: String, payload: Map<String, Any?>): String {
        val id = "e_${++sequence}"
        try {
            val data = JSONObject(mapOf("id" to id, "seq" to sequence, "kind" to kind,
                "session_id" to session, "wall_time_ms" to System.currentTimeMillis(),
                "uptime_ms" to SystemClock.uptimeMillis(), "payload" to payload)).toString() + "\n"
            FileOutputStream(File(folder, "journal.jsonl"), true).use {
                it.write(data.toByteArray(Charsets.UTF_8)); it.fd.sync()
            }
            count = sequence
        } catch (e: Exception) { failure = "事件保存失败: ${e.javaClass.simpleName}"; paused = true }
        return id
    }

    private fun atomicJson(file: File, data: Map<String, Any?>) {
        val temp = File(file.path + ".tmp")
        FileOutputStream(temp).use { it.write(JSONObject(data).toString().toByteArray(Charsets.UTF_8)); it.fd.sync() }
        check(temp.renameTo(file))
    }

    fun bounds(rect: Rect): Map<String, Int> = mapOf("left" to rect.left, "top" to rect.top,
        "right" to rect.right, "bottom" to rect.bottom)
}
