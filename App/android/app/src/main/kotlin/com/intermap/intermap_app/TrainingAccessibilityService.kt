package com.intermap.intermap_app

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.graphics.Rect
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.Button
import android.widget.Toast
import kotlin.math.abs

class TrainingAccessibilityService : AccessibilityService() {
    companion object {
        @Volatile var connected = false
        var onEvent: ((Map<String, Any?>) -> Unit)? = null
        private var instance: TrainingAccessibilityService? = null
        private val mainHandler = Handler(Looper.getMainLooper())

        fun refreshCompletionOverlay() {
            mainHandler.post { instance?.updateCompletionOverlay() }
        }
    }

    private var completionButton: Button? = null
    private var completionParams: WindowManager.LayoutParams? = null

    override fun onServiceConnected() {
        connected = true
        instance = this
        updateCompletionOverlay()
    }
    override fun onInterrupt() { TrainingRecorder.record("capture_gap", mapOf("reason" to "accessibility_interrupted")) }
    override fun onDestroy() {
        hideCompletionOverlay()
        instance = null
        connected = false
        super.onDestroy()
    }

    private fun updateCompletionOverlay() {
        val visible = TrainingRecorder.active && !TrainingRecorder.paused &&
            TrainingRecorder.canConfirmTask &&
            TrainingRecorder.foregroundPackage == TrainingRecorder.selectedPackage
        if (!visible) { hideCompletionOverlay(); return }
        if (completionButton != null) return
        val density = resources.displayMetrics.density
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.END or Gravity.BOTTOM
            x = (16 * density).toInt()
            y = (100 * density).toInt()
        }
        val button = Button(this).apply {
            text = "任务完成"
            contentDescription = "确认本次训练目标已经完成"
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.rgb(43, 126, 62))
            minHeight = (56 * density).toInt()
            setPadding((18 * density).toInt(), 0, (18 * density).toInt(), 0)
            setOnClickListener {
                isEnabled = false
                TrainingRecorder.confirmTaskCompleted { state ->
                    mainHandler.post {
                        val error = state["confirmation_error"] as? String
                        if (error == null) {
                            hideCompletionOverlay()
                            Toast.makeText(this@TrainingAccessibilityService, "已记录任务完成，正在上传", Toast.LENGTH_SHORT).show()
                        } else {
                            isEnabled = true
                            Toast.makeText(this@TrainingAccessibilityService, error, Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            }
        }
        var downX = 0f
        var downY = 0f
        var startX = 0
        var startY = 0
        var moved = false
        button.setOnTouchListener { view, event ->
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = event.rawX; downY = event.rawY
                    startX = params.x; startY = params.y
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = event.rawX - downX
                    val dy = event.rawY - downY
                    if (abs(dx) > 12 * density || abs(dy) > 12 * density) moved = true
                    if (moved) {
                        params.x = (startX - dx).toInt().coerceAtLeast(0)
                        params.y = (startY - dy).toInt().coerceAtLeast(0)
                        (getSystemService(Context.WINDOW_SERVICE) as WindowManager).updateViewLayout(view, params)
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) view.performClick()
                    true
                }
                else -> true
            }
        }
        try {
            (getSystemService(Context.WINDOW_SERVICE) as WindowManager).addView(button, params)
            completionButton = button
            completionParams = params
        } catch (_: Exception) {
            TrainingRecorder.record("capture_gap", mapOf("reason" to "completion_overlay_unavailable"))
        }
    }

    private fun hideCompletionOverlay() {
        val button = completionButton ?: return
        completionButton = null
        completionParams = null
        try { (getSystemService(Context.WINDOW_SERVICE) as WindowManager).removeView(button) }
        catch (_: Exception) {}
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        try { capture(event) } catch (error: Exception) {
            TrainingRecorder.privacyUnknown = true
            TrainingRecorder.record("capture_gap", mapOf("reason" to "accessibility_snapshot_error", "error" to error.javaClass.simpleName))
        }
    }

    private fun capture(event: AccessibilityEvent) {
        if (event.packageName?.toString() == packageName) return
        val root = rootInActiveWindow
        TrainingRecorder.foregroundPackage = root?.packageName?.toString().orEmpty()
        updateCompletionOverlay()
        val recording = TrainingRecorder.active && !TrainingRecorder.paused
        if (recording && TrainingRecorder.foregroundPackage != TrainingRecorder.selectedPackage) {
            TrainingRecorder.privacyUnknown = true
            return
        }
        if (root?.packageName?.toString() == packageName) return
        val masks = mutableListOf<Rect>()
        var count = 0
        var truncated = false
        fun read(node: AccessibilityNodeInfo, depth: Int): Map<String, Any?> {
            count++
            val rect = Rect(); node.getBoundsInScreen(rect)
            val privateInput = node.isPassword || node.isEditable
            if (privateInput) masks.add(Rect(rect))
            val children = mutableListOf<Map<String, Any?>>()
            if (depth < 24) for (i in 0 until node.childCount) {
                if (count >= 400) { truncated = true; break }
                val child = node.getChild(i) ?: continue
                children.add(read(child, depth + 1))
                @Suppress("DEPRECATION") child.recycle()
            } else if (node.childCount > 0) truncated = true
            return mapOf("text" to if (privateInput) null else node.text?.toString()?.take(500),
                "description" to if (privateInput) null else node.contentDescription?.toString()?.take(500),
                "view_id" to node.viewIdResourceName, "class_name" to node.className?.toString(),
                "bounds" to TrainingRecorder.bounds(rect), "clickable" to node.isClickable,
                "scrollable" to node.isScrollable, "editable" to node.isEditable,
                "password" to node.isPassword, "enabled" to node.isEnabled,
                "selected" to node.isSelected, "checked" to node.isChecked,
                "children" to children)
        }
        val tree = root?.let { read(it, 0) }
        TrainingRecorder.maskedBounds = masks
        TrainingRecorder.privacyUnknown = root == null || truncated
        val source = event.source
        val sourceInfo = source?.let {
            val rect = Rect(); it.getBoundsInScreen(rect)
            val privateInput = it.isPassword || it.isEditable
            mapOf("text" to if (privateInput) null else it.text?.toString()?.take(500),
                "description" to if (privateInput) null else it.contentDescription?.toString()?.take(500),
                "view_id" to it.viewIdResourceName, "bounds" to TrainingRecorder.bounds(rect),
                "class_name" to it.className?.toString(), "editable" to privateInput)
        }
        val payload = mapOf("event_type" to event.eventType, "event_uptime_ms" to event.eventTime,
            "observed_uptime_ms" to SystemClock.uptimeMillis(), "package_name" to event.packageName?.toString(),
            "window_id" to event.windowId, "source" to sourceInfo, "tree" to tree,
            "tree_truncated" to truncated, "node_count" to count,
            "scroll_x" to event.scrollX, "scroll_y" to event.scrollY,
            "from_index" to event.fromIndex, "to_index" to event.toIndex,
            "position_source" to if (sourceInfo != null) "accessibility_node_bounds" else "unavailable",
            "touch_point" to null)
        if (recording) TrainingRecorder.event(payload)
        // Keep the legacy navigation interface available without using it as training ground truth.
        val texts = mutableListOf<Map<String, Any?>>()
        fun flatten(node: Map<String, Any?>) {
            val text = node["text"] ?: node["description"]
            if (text != null) texts.add(mapOf("capturedText" to text))
            @Suppress("UNCHECKED_CAST")
            (node["children"] as? List<Map<String, Any?>>)?.forEach { flatten(it) }
        }
        tree?.let { flatten(it) }
        onEvent?.invoke(mapOf("eventType" to event.eventType, "packageName" to event.packageName?.toString(),
            "capturedText" to sourceInfo?.get("text"), "nodeId" to sourceInfo?.get("view_id"),
            "subNodesActions" to texts))
        @Suppress("DEPRECATION") source?.recycle()
        @Suppress("DEPRECATION") root?.recycle()
    }
}
