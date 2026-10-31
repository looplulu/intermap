package com.intermap.intermap_app

import android.app.Activity
import android.graphics.*
import android.view.*
import android.widget.*

class CompanionOverlay(private val activity: Activity, private val action: (String, String) -> Unit) {
    companion object {
        private var instance: CompanionOverlay? = null
        fun mask(bitmap: Bitmap) {
            val view = instance?.root ?: return
            val xy = IntArray(2); view.getLocationOnScreen(xy)
            Canvas(bitmap).drawRect(xy[0].toFloat(),xy[1].toFloat(),(xy[0]+view.width).toFloat(),(xy[1]+view.height).toFloat(),Paint().apply { color=Color.LTGRAY })
        }
    }
    private val wm = activity.getSystemService(Activity.WINDOW_SERVICE) as WindowManager
    private var root: LinearLayout? = null
    private var expanded = false
    private var message = "点这里，告诉小路你想做什么"
    private var goal = ""
    private fun dp(v: Int) = (v*activity.resources.displayMetrics.density).toInt()
    private val params = WindowManager.LayoutParams(160,120,WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT).apply { gravity=Gravity.TOP or Gravity.END; x=16; y=360 }
    fun show() { instance=this; render() }
    fun hide() { root?.let { wm.removeView(it) }; root=null; if(instance===this) instance=null }
    fun update(text: String) { message=text; if(expanded && root!=null) render() }
    private fun render() {
        root?.let { wm.removeView(it) }
        val box=LinearLayout(activity).apply { orientation=LinearLayout.VERTICAL; setPadding(dp(10),dp(6),dp(10),dp(6)); setBackgroundColor(Color.rgb(240,249,242)) }
        root=box; params.width=dp(if(expanded) 290 else 76); params.height=WindowManager.LayoutParams.WRAP_CONTENT
        params.flags=WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or (if(expanded) 0 else WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE)
        val title=Button(activity).apply { text=if(expanded) "小路 · 收起" else "小路"; textSize=18f }
        var sy=0f; var sx=0f; var oy=0; var ox=0; var moved=false
        title.setOnTouchListener { _,e -> when(e.actionMasked) {
            MotionEvent.ACTION_DOWN -> { sy=e.rawY; sx=e.rawX; oy=params.y; ox=params.x; moved=false; true }
            MotionEvent.ACTION_MOVE -> { val dy=e.rawY-sy; val dx=e.rawX-sx; if(kotlin.math.abs(dx)+kotlin.math.abs(dy)>dp(10)) moved=true
                if(moved) {
                    val screen=activity.resources.displayMetrics
                    params.y=(oy+dy).toInt().coerceIn(0,(screen.heightPixels-box.height).coerceAtLeast(0))
                    params.x=(ox-dx).toInt().coerceIn(0,(screen.widthPixels-box.width).coerceAtLeast(0))
                    wm.updateViewLayout(box,params)
                }; true }
            MotionEvent.ACTION_UP -> { if(!moved) { expanded=!expanded; render() }; true }
            else -> false
        } }
        box.addView(title)
        if(expanded) {
            val content=LinearLayout(activity).apply { orientation=LinearLayout.VERTICAL }
            box.addView(ScrollView(activity).apply { addView(content) },LinearLayout.LayoutParams(-1,dp(440).coerceAtMost(activity.resources.displayMetrics.heightPixels-dp(140))))
            content.addView(TextView(activity).apply { text=message; textSize=18f; setTextColor(Color.DKGRAY) })
            val input=EditText(activity).apply { setText(goal); hint="你想做什么？"; textSize=18f; maxLines=3 }; content.addView(input)
            fun button(label: String,event: String) { content.addView(Button(activity).apply { text=label; setOnClickListener {
                goal=input.text.toString().trim(); expanded=false; render(); action(event,goal)
            } }) }
            button("开始新任务","start"); button("说出目标","voice"); button("重听这一步","repeat")
            button("暂停 / 继续","pause"); button("没有找到","not_found"); button("这一步不对","wrong_step")
            button("我已完成","completed"); button("结束任务","cancelled")
        }
        wm.addView(box,params)
    }
}
