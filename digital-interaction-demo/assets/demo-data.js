// 数字交互引擎 Demo 数据
// 预置演示数据只用于“不上传视频/不开摄像头”的演示模式。
// 上传录屏或摄像头模式下，系统必须先 OCR 当前画面，再用这些节点作为 Golden Flow 地图知识匹配。

var DEMO_DATA = {
  taobao_refund: {
    app: "淘宝",
    task: "退款",
    description: "淘宝退款标准流程",
    duration: 22,
    steps: [
      {t:0, n:"淘宝首页", node_id:"taobao_home", g:"点底部右边的'我的淘宝'，先进入个人中心。", c:95, s:"gf", r:[]},
      {t:3, n:"个人中心", node_id:"taobao_mine", g:"找到'我的订单'，点旁边的'全部'。", c:95, s:"gf", r:[]},
      {t:6, n:"订单列表", node_id:"taobao_order_list", g:"在订单列表里找到要退款的商品，点进订单详情。", c:90, s:"gf", r:[]},
      {t:9, n:"订单详情", node_id:"taobao_order_detail", g:"点商品下方或底部的'申请售后'，同时看一眼是否支持'7天无理由退换'。", c:95, s:"gf", r:["注意'7天无理由退换'是否已过期，过期后商家可能拒绝"]},
      {t:13, n:"售后类型", node_id:"taobao_aftersales_type", g:"选择'退货/退款'；如果商品没收到或不用退货，再选'仅退款'。然后点'下一步'。", c:95, s:"gf", r:["售后类型选错会影响退款路径，先确认商品是否需要寄回"]},
      {t:16, n:"退款原因", node_id:"taobao_aftersales_reason", g:"选一个最符合真实情况的退款原因，再点'下一步'。", c:95, s:"gf", r:["原因要如实选择，原因不一致可能影响审核"]},
      {t:19, n:"提交退款", node_id:"taobao_refund_submit", g:"核对退款金额、说明和商品信息，确认没问题再点'提交'。", c:95, s:"gf", r:["提交后流程会进入商家审核，先想清楚再点"]},
      {t:22, n:"退款结果", node_id:"taobao_refund_result", g:"退款申请已经提交，之后在退款进度里看商家处理结果。", c:95, s:"gf", r:[]}
    ]
  },
  taobao_order: {
    app: "淘宝",
    task: "下单",
    description: "淘宝购物车下单标准流程",
    duration: 28,
    steps: [
      {t:0, n:"购物车", node_id:"taobao_cart", g:"确认要买的商品都勾选了，看下合计金额对不对", c:95, s:"gf", r:[]},
      {t:4, n:"购物车", node_id:"taobao_cart", g:"有红色'去结算'按钮就点它，在底部右边", c:95, s:"gf", r:["有凑单优惠的话可以先看看，不需要就跳过"]},
      {t:8, n:"确认订单", node_id:"taobao_confirm_order", g:"先看收货地址对不对，'恒大四季上东'这个地址要是你的", c:95, s:"gf", r:["地址不对要点旁边修改"]},
      {t:12, n:"确认订单", node_id:"taobao_confirm_order", g:"看下'退货权益'，88VIP有退货包运费，确认没问题", c:95, s:"gf", r:[]},
      {t:15, n:"优惠详情", node_id:"taobao_order_discount", g:"这里能看到各店铺的优惠明细，消费券和红包各减了多少", c:90, s:"gf", r:[]},
      {t:18, n:"确认订单", node_id:"taobao_confirm_order", g:"确认地址、商品、优惠都没问题，点'提交订单'", c:95, s:"gf", r:["提交后会在15分钟内自动取消，不付款的话"]},
      {t:22, n:"支付页", node_id:"taobao_pay_success", g:"选支付方式，支付宝或微信，确认金额，点'立即付款'", c:95, s:"gf", r:["付款前确认金额，尤其用了消费券红包的"]},
      {t:26, n:"支付成功", node_id:"taobao_pay_success", g:"支付成功了，能看到淘气值和商品数量，点'查看订单'看详情", c:95, s:"gf", r:[]},
      {t:28, n:"支付成功", node_id:"taobao_pay_success", g:"也可以直接回首页继续逛，订单在我的订单里能找到", c:95, s:"gf", r:[]}
    ]
  },
  jd_refund: {
    app: "京东",
    task: "退款",
    description: "京东退款/退货标准流程",
    duration: 28,
    steps: [
      {t:0, n:"京东首页", node_id:"jd_home", g:"点底部最右边的'我的'，进入个人中心。", c:95, s:"gf", r:[]},
      {t:3, n:"个人中心", node_id:"jd_mine", g:"找到'我的订单'，点'全部'进入订单列表。", c:95, s:"gf", r:[]},
      {t:6, n:"订单列表", node_id:"jd_order_list", g:"找到要退款的商品订单，点进订单详情。", c:90, s:"gf", r:[]},
      {t:9, n:"订单详情", node_id:"jd_order_detail", g:"点底部或订单操作区的'退款/售后'。", c:95, s:"gf", r:["如果页面写着不支持7天无理由，商家可能拒绝退货"]},
      {t:12, n:"售后中心", node_id:"jd_aftersales_hub", g:"在售后中心里找到对应商品，点旁边的'退款/售后'。", c:90, s:"gf", r:[]},
      {t:15, n:"售后类型", node_id:"jd_aftersales_type", g:"根据实际情况选'退货'或'仅退款'；如果只是降价，也可以选'价格保护'。", c:95, s:"gf", r:["价格保护只适合降价退差价，不等于退货退款"]},
      {t:19, n:"退款原因", node_id:"jd_aftersales_reason", g:"选择最符合实际情况的申请原因，然后点'确认'。", c:95, s:"gf", r:["原因选错可能影响审核，如实选就行"]},
      {t:23, n:"提交退款", node_id:"jd_refund_submit", g:"核对退款金额和说明，没问题再点'提交'。", c:95, s:"gf", r:["提交后会进入审核，先确认金额和商品"]},
      {t:26, n:"退款结果", node_id:"jd_refund_result", g:"退款申请已经提交，后续在退换/售后里查看进度。", c:95, s:"gf", r:[]}
    ]
  },
  wechat_video_shop: {
    app: "微信",
    task: "视频号购物",
    description: "微信视频号查看订单和物流",
    duration: 24,
    steps: [
      {t:0, n:"微信首页", g:"点底部'发现'，在底部中间偏右", c:95, s:"gf", r:[]},
      {t:3, n:"发现页", g:"点'视频号'，在顶部第一个", c:95, s:"gf", r:[]},
      {t:6, n:"直播列表", g:"找到想看的直播，点进去", c:90, s:"gf", r:[]},
      {t:9, n:"个人页", g:"点'小店与卡包'，在左边", c:95, s:"gf", r:[]},
      {t:12, n:"小店中心", g:"点'订单'看买的商品，在左边", c:95, s:"gf", r:[]},
      {t:15, n:"订单列表", g:"找到你要看的订单，点进去", c:90, s:"gf", r:[]},
      {t:18, n:"订单详情", g:"如果要退款，点'退款售后'。如果收到了货，点'确认收货'", c:95, s:"gf", r:["有自动确认收货倒计时，超时自动确认，确认后退款更难"]},
      {t:21, n:"物流详情", g:"这里能看到快递到哪了。点左上角返回订单", c:95, s:"gf", r:[]}
    ]
  },
  meituan_order: {
    app: "美团",
    task: "点外卖",
    description: "美团点外卖标准流程",
    duration: 28,
    steps: [
      {t:0, n:"美团首页", g:"点顶部第一个图标'外卖'，在顶部左边", c:95, s:"gf", r:[]},
      {t:3, n:"外卖首页", g:"顶部确认收货地址，然后搜想吃的或者往下看推荐", c:90, s:"gf", r:["确认地址是不是你现在的位置"]},
      {t:6, n:"店铺列表", g:"看哪家顺眼就点进去，注意起送价和配送费", c:85, s:"gf", r:[]},
      {t:10, n:"店铺菜单", g:"点你想吃的菜，可以点多个", c:90, s:"gf", r:[]},
      {t:14, n:"店铺菜单", g:"选好了点右下角'去结算'", c:95, s:"gf", r:["看清楚满减活动，差一点能凑到优惠"]},
      {t:18, n:"确认订单", g:"确认地址和菜品，有备注可以加，点'提交订单'", c:90, s:"gf", r:["如果饿了么红包可以在这里抵扣"]},
      {t:22, n:"支付页", g:"选支付方式，微信或支付宝都行，点'立即支付'", c:95, s:"gf", r:[]},
      {t:25, n:"下单成功", g:"下单成功了，能看到预计送达时间", c:95, s:"gf", r:[]}
    ]
  },
  gaode_navigate: {
    app: "高德地图",
    task: "导航",
    description: "高德地图导航到目的地",
    duration: 20,
    steps: [
      {t:0, n:"高德首页", g:"点顶部搜索框，输入你想去的地方", c:95, s:"gf", r:[]},
      {t:3, n:"搜索结果", g:"在列表里找到正确的地址，点右边'到这去'", c:90, s:"gf", r:["注意看地址全称，别选错了"]},
      {t:6, n:"路线规划", g:"选'驾车'或'步行'或'公交'，看你出行方式", c:90, s:"gf", r:[]},
      {t:9, n:"路线规划", g:"看推荐路线和时间，确认没问题点'开始导航'", c:95, s:"gf", r:[]},
      {t:12, n:"导航中", g:"导航开始了，听语音提示转弯就行", c:95, s:"gf", r:["开车的时候把手机放支架上"]},
      {t:17, n:"到达", g:"到达目的地了，导航结束", c:95, s:"gf", r:[]}
    ]
  },
  alipay_scan: {
    app: "支付宝",
    task: "扫码支付",
    description: "支付宝扫码付款",
    duration: 15,
    steps: [
      {t:0, n:"支付宝首页", g:"点右上角的'扫码'，在顶部右边", c:95, s:"gf", r:[]},
      {t:3, n:"扫一扫", g:"对准商家的收款码，手机会自动识别", c:95, s:"gf", r:[]},
      {t:6, n:"付款页", g:"看清楚金额，确认是对的再付", c:90, s:"gf", r:["一定看清楚金额再付款"]},
      {t:9, n:"付款页", g:"金额没问题就点'确认付款'", c:95, s:"gf", r:[]},
      {t:12, n:"付款成功", g:"付款成功了，给商家看一下就行", c:95, s:"gf", r:[]}
    ]
  }
};

var APP_TASKS = {};
Object.keys(DEMO_DATA).forEach(function(key) {
  var d = DEMO_DATA[key];
  if (!APP_TASKS[d.app]) APP_TASKS[d.app] = [];
  APP_TASKS[d.app].push({
    key: key,
    task: d.task,
    description: d.description,
    duration: d.duration,
    stepCount: d.steps.length
  });
});

// 文件名匹配规则
var VIDEO_MATCH_RULES = [
  {pattern: /taobao.*order|淘宝.*下单/i, key: 'taobao_order'},
  {pattern: /taobao|淘宝/i, key: 'taobao_refund'},
  {pattern: /jd|京东/i, key: 'jd_refund'},
  {pattern: /wechat|微信|视频号/i, key: 'wechat_video_shop'},
  {pattern: /meituan|美团|外卖/i, key: 'meituan_order'},
  {pattern: /gaode|高德|导航/i, key: 'gaode_navigate'},
  {pattern: /alipay|支付宝|扫码/i, key: 'alipay_scan'}
];
