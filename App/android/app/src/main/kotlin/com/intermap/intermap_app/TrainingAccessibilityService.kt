package com.intermap.intermap_app

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

class TrainingAccessibilityService : AccessibilityService() {
    companion object {
        @Volatile var connected = false
        var onEvent: ((Map<String, Any?>) -> Unit)? = null
    }

    override fun onServiceConnected() { connected = true }
    override fun onInterrupt() { TrainingRecorder.record("capture_gap", mapOf("reason" to "accessibility_interrupted")) }
    override fun onDestroy() { connected = false; super.onDestroy() }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        try { capture(event) } catch (error: Exception) {
            TrainingRecorder.privacyUnknown = true
            TrainingRecorder.record("capture_gap", mapOf("reason" to "accessibility_snapshot_error", "error" to error.javaClass.simpleName))
        }
    }

    private fun capture(event: AccessibilityEvent) {
        val root = rootInActiveWindow
        TrainingRecorder.foregroundPackage = root?.packageName?.toString().orEmpty()
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
