# Douyin APK Static Analysis

Analysis date: 2026-09-03

For the expanded 2026-10-25 evidence atlas, see
[12-douyin-apk-flow-atlas.md](12-douyin-apk-flow-atlas.md). That analysis separates
static bindings and code routes from complete, real-device-validated task flows.

This document records APK-derived evidence only. It must not be promoted to
Golden Flow without real-device validation.

## Sample provenance

- Source page: `https://www.douyin.com/downloadpage/app`
- Official 64-bit download link exposed by the Douyin page bundle:
  `https://ugapk.com/mGFG`
- Package: `com.ss.android.ugc.aweme`
- Version: `40.3.0` (`versionCode` 400301)
- APK size: 354,399,336 bytes
- SHA-256:
  `e4fcd60500d25e1749ce7e6733e534b770d5bbaaab4699d673fc27a6bb499f64`
- Signer: `CN=Aweme Douyin, OU=ByteDance, O=ByteDance, L=Beijing, ST=Beijing, C=CN`
- Signer certificate SHA-256:
  `5182ae3b1b85337bb182cf24882449f84447ded18e296a747a9f6a0a2622512e`
- APK signature verification: v1, v2 and v3 valid

The APK itself is not committed to Git. It is a temporary analysis sample.

## Confirmed static evidence

1. The manifest registers
   `com.bytedance.android.shopping.orderlist.list.container.OrderListActivity`.
   The native router key is `ecom_order_list`, and the activity accepts
   `ORDER_LIST_URI` plus `ORDER_LIST_PARAM`.
2. The app contains an offline `ecommerce_order_list_component` package. Its
   header renders `我的订单`, its `to_all_tab` component emits `toAllTab`, and
   its product row emits a server-provided click event or `jumpRight`.
3. The order list contains tab, product, order-button and per-order refund
   components. Product names, statuses, action names and most visible labels
   are supplied as runtime data.
4. The order implementation requests its schema and content from server APIs:
   `order/getOrderListSchema`, `order/yata/orderListQuery`, and
   `order/yata/orderListQueryStream`.
5. The APK exposes order/refund capabilities including `openEcOrderDetail`,
   `applyRefund`, `refund-apply`, `refund-detail`, and `trade-order-detail`.
6. `AllOrderPageStruct` contains a server-supplied `url` and `text` and is
   returned as `all_order_page`. This confirms that an order entry's visible
   name and destination can change without an APK update.

## Golden Flow cross-check

The current verified path remains consistent with the APK evidence:

```text
Douyin home
-> profile
-> order entry
-> order center / all orders
-> user selects the target product
-> order detail
-> apply for refund
```

The strongest corroboration is the explicit all-orders action, clickable
product rows, a separate order-detail capability, and refund-application
capabilities. This supports keeping `全部订单 -> 选择商品 -> 订单详情 -> 申请退款`
as the main route.

The APK also models existing after-sale state and per-order refund information.
This is consistent with treating `退款/售后` as an after-sale management area,
not as a universally safe shortcut for starting a new refund. The exact label,
position and availability still require live GUI/accessibility evidence.

## What the APK cannot prove

- The exact current profile-page entrance or its screen position.
- Whether the entrance currently says `我的订单`, `查看全部订单`, or another
  server-provided/A-B-tested label.
- The exact tabs and buttons shown for a particular account, order state,
  product type, region or app experiment.
- The coordinates a user should tap.
- A complete interaction map. Commerce UI is partly server-driven and can be
  updated independently of the APK.

## Data isolation and priority

Store conclusions from this analysis with source type `apk_static`. For
user-visible navigation, use this priority:

```text
live_verified > video_derived > apk_static > web_unverified
```

`apk_static` may propose candidate nodes, routes and synonyms. It must never
overwrite `live_verified` nodes automatically. When screenshot text differs
from a stored label, navigation must speak the text visible in the current GUI.

