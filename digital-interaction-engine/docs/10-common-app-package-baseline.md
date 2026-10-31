# 常用 App 安装包静态基线

生成日期：2026-09-04

这份基线覆盖微信、抖音、快手、小红书、淘宝、京东、拼多多、美团、
美团外卖和淘宝闪购。它的用途是给真机训练提供候选词、候选入口和版本
身份，不是直接生成完整交互地图。

## 完成情况

- Android：10/10 个应用已经完成 APK 获取、完整性校验、签名验证和静态分析。
- iOS：10/10 个应用已经完成 App Store 官方元数据建档。
- Android 来源：抖音使用抖音官网安装包，其余应用使用腾讯应用宝官方分发包。
- iOS 边界：不绕过 FairPlay，不使用破解或解密 IPA；页面与跳转必须通过真机训练确认。
- 2026-09-04 的初始流程曾把安装包保存在服务器；该做法已被
  2026-10-25 的存储规则取代：下载与反推在本机完成，安装包仅临时使用，
  结果核对保存后删除。服务器只保留必要的结构化证据和来源记录。

## 版本矩阵

| App | Android 包名 | Android 样本 | iOS Bundle ID | iOS 版本 | 最低 iOS |
|---|---|---:|---|---:|---:|
| 微信 | `com.tencent.mm` | 8.0.77 | `com.tencent.xin` | 8.0.76 | 15.0 |
| 抖音 | `com.ss.android.ugc.aweme` | 40.3.0 | `com.ss.iphone.ugc.Aweme` | 40.3.0 | 15.0 |
| 快手 | `com.smile.gifmaker` | 14.8.10.50114 | `com.jiangjia.gif` | 14.7.40 | 13.0 |
| 小红书 | `com.xingin.xhs` | 9.45.0 | `com.xingin.discover` | 9.45.2 | 13.0 |
| 淘宝 | `com.taobao.taobao` | 10.66.0 | `com.taobao.taobao4iphone` | 10.66.0 | 13.0 |
| 京东 | `com.jingdong.app.mall` | 15.10.50 | `com.360buy.jdmobile` | 15.10.71 | 13.0 |
| 拼多多 | `com.xunmeng.pinduoduo` | 8.22.0 | `com.xunmeng.pinduoduo` | 8.23.0 | 13.0 |
| 美团 | `com.sankuai.meituan` | 12.65.203 | `com.meituan.imeituan` | 12.65.202 | 13.0 |
| 美团外卖 | `com.sankuai.meituan.takeoutnew` | 8.81.2 | `com.meituan.itakeaway` | 8.81.10 | 13.0 |
| 淘宝闪购 | `me.ele` | 12.8.88 | `me.ele.ios.eleme` | 12.8.68 | 13.2 |

版本号是抓取当天的样本身份，不应被当成长期固定值。每次应用升级后应重新
生成报告，并把不同版本保留为独立目录。

## Android 产物

每个报告都包含：

1. 分发方文件大小与 MD5、项目侧 SHA-256；
2. 实际包名、版本号、目标 Android SDK；
3. APK 签名是否有效、签名者名称和证书指纹；
4. Manifest 中可能与交互有关的 Activity、Service、Receiver 和 Provider；
5. 资源文字、DEX 类名和 assets 中的候选交互证据；
6. 文件、DEX、原生库和 ABI 数量；
7. 固定的 `apk_static` 来源和 `pending_review` 状态。

服务器目录：

```text
/var/www/intermap-data/package_static/inventory-current.json
/var/www/intermap-data/package_static/android/<app>/<version>/analysis.json
/var/www/intermap-data/package_static/android/douyin/40.3.0/analysis-vendor.json
```

本机分析工具位于项目目录：

```text
scripts/mobile_package_lab.py
scripts/extract_apk_flows.py
```

报告和来源记录按应用及版本隔离，APK 不进入 Git，也不再作为服务器存档。
服务器上的旧工具副本不是后续反推任务的执行位置。

## 已得到的有效结论

- 抖音包明确存在全部订单、订单详情和申请退款能力，也证明订单列表文字和
  跳转大量由服务端动态下发。它支持当前
  `全部订单 -> 选择商品 -> 订单详情 -> 申请退款` 主路径，但不能证明屏幕坐标。
- 拼多多包能直接提取到订单、支付、物流、评价、退款/售后、客服、地址和
  优惠券等候选文字，说明安装包很适合建立“待真机验证的功能目录”。
- 美团与美团外卖使用相同签名证书，可作为同一发布主体的额外交叉证据；
  这不代表两个 App 的页面节点可以合并。
- 其余应用也已生成相同结构的候选报告。候选数量不是地图完整度，混淆代码、
  历史兼容代码和未启用功能都可能产生静态误报。

## 为什么不能仅靠安装包得到全部交互

安装包能证明“客户端具备某种能力”，却不能证明“当前用户一定会看到某个
页面”。首页运营位、登录状态、账号权限、地区、订单状态、A/B 实验、WebView、
小程序和服务端下发页面都可能在不更新安装包的情况下改变。

因此静态结果只能进入候选池：

```text
apk_static + pending_review
    -> 与真机画面、无障碍点击和人工标注对齐
    -> 形成候选 Node / Edge / 同义词
    -> 人工审核
    -> 才能修正或扩充 Golden Flow
```

冲突时采用以下优先级：

```text
live_android_accessibility
> live_android_screen
> live_web_training
> video_derived
> apk_static
> web_unverified
```

## iOS 验证方式

iOS 当前只建立了官方 Bundle ID、版本、卖方、最低系统版本、商店链接和公开
图标。真正的页面节点通过 iPhone 真机或 iPhone 镜像训练获得，并至少记录：

- App 版本；
- iOS 大版本和设备类型；
- 登录、地区、会员和订单等影响页面的状态；
- GUI 截图指纹、OCR 文字和人工标注；
- 操作前后页面及点击目标。

iOS 18 与 iOS 26 等明显不同的界面必须保存为环境变体，不能强行合并成一个
节点坐标。

## 建议训练顺序

1. 继续完成抖音，先把一条 App 的采集、审核、纠错和导航闭环打磨稳定。
2. 淘宝、京东、拼多多，用相似任务交叉验证订单、客服和售后本体。
3. 美团、美团外卖、淘宝闪购，补充地址、门店、配送和即时零售状态。
4. 微信、快手、小红书，最后处理社交关系、内容流和账号状态带来的高变体页面。

这个顺序比同时铺开十个 App 更容易发现数据结构问题，也符合“真实训练优先”
的项目原则。
