#!/usr/bin/env python3
"""Extract attributable APK UI bindings and conservative bytecode navigation.

This is static, unreviewed evidence. It never writes a published navigation map.
Requires androguard 4.1.3; process one DEX at a time to bound memory use.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gc
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import zipfile


ANDROID = "{http://schemas.android.com/apk/res/android}"
CACHE_VERSION = 5
MODULES = [
    ("orders", "订单与售后", r"order|refund|aftersale|after_sale|reimburse|物流|订单|售后|退款"),
    ("checkout", "商品、购物车与结算", r"ecom|commerce|shopping|buynow|sku|pdp|coupon|cart|shop|mall|pay|wallet|recharge|cash|商品|支付|钱包"),
    ("account", "账号、登录与安全", r"account|login|passport|bindphone|security|verify|密码|登录|账号"),
    ("settings", "设置、隐私与帮助", r"setting|privacy|permission|feedback|help|agreement|设置|隐私|帮助"),
    ("search", "搜索与发现", r"search|discover|搜索"),
    ("profile", "个人主页与关系", r"profile|favorite|collection|follow|friend|fans|个人|收藏|关注"),
    ("messages", "消息、聊天与分享", r"message|chat|conversation|im_|share|contact|消息|聊天|分享"),
    ("create", "拍摄、创作与发布", r"camera|record|publish|editor|edit_|draft|剪辑|拍摄|发布"),
    ("live", "直播与互动", r"live|直播"),
    ("local", "本地生活与服务", r"poi|life|delivery|takeout|location|map|团购|外卖"),
    ("video", "视频、播放与评论", r"video|feed|play|comment|detail|douyin|aweme|视频|评论"),
    ("other", "其他与基础组件", r"."),
]

NAMES = {
    "ecommerce_order_list_component": "订单列表组件",
    "ecom_buynow_card_template": "下单确认组件",
    "ecom_cart_card_template": "购物车组件",
    "ecom_sku_pannel_template": "商品规格组件",
    "ecom_pdp_card_template": "商品详情组件",
    "pdp_slice_template": "商品详情切片",
    "to_all_tab": "查看全部订单入口", "product_line": "订单商品行",
    "per_order_refund": "单笔订单售后信息", "order_list_header_search": "订单列表搜索头部",
    "top_entrance": "顶部功能入口", "submit_order_bar": "提交订单操作栏",
    "order_card": "订单卡片", "order_list_tabbar": "订单分类标签",
    "order_list_tab_bar": "订单分类标签", "order_filter_card": "订单筛选",
    "address_card": "地址卡片", "address_editor": "地址编辑组件",
    "shop_line": "店铺信息行", "price_line": "价格信息行",
    "search_result_header": "搜索结果头部", "head": "头部区域",
}


def ident(*parts):
    return hashlib.sha256("\0".join(map(str, parts)).encode()).hexdigest()[:18]


def module_for(value):
    for key, _, pattern in MODULES:
        if re.search(pattern, value, re.I):
            return key
    return "other"


def pretty_name(path):
    parts = path.split("/")
    name = parts[-2] if parts[-1] in ("main.json", "template.js") else Path(path).stem
    return NAMES.get(name, name)


def walk_json(value, path="$", inherited=None):
    conditions = list(inherited or [])
    if isinstance(value, dict):
        for key in ("if", ":if", "condition", "show_if", "visibility"):
            if key in value:
                conditions.append({"path": path + "." + key, "value": value[key]})
        yield path, value, conditions
        for key, child in value.items():
            yield from walk_json(child, path + "." + key, conditions)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_json(child, path + f"[{index}]", conditions)


def text_values(value):
    result = []
    for path, obj, _ in walk_json(value):
        for key, item in obj.items():
            if key in ("text", "aria_label", "contentDescription", "title", "label") and isinstance(item, str):
                result.append({"path": path + "." + key, "value": item, "dynamic": False})
            elif key in (":text", ":aria_label", ":title", ":label"):
                result.append({"path": path + "." + key, "value": item, "dynamic": True})
    return result


def action_kind(action):
    if isinstance(action, str):
        return "static_binding", action
    if isinstance(action, dict) and isinstance(action.get("type"), str):
        return "static_binding", action["type"]
    return "runtime_value", json.dumps(action, ensure_ascii=False, separators=(",", ":"))


def template_graph(path, data):
    bindings = []
    for location, obj, conditions in walk_json(data):
        for key in ("click_action", ":click_action", "long_click_action", ":long_click_action", "onClick", "onLongClick", "tap_action"):
            if key not in obj:
                continue
            action = obj[key]
            status, event = action_kind(action)
            if key.startswith(":"):
                status = "runtime_value"
                event = action if isinstance(action, str) else json.dumps(action, ensure_ascii=False, separators=(",", ":"))
            attrs = obj.get("attr", {})
            local_text = text_values(obj)
            bindings.append({
                "id": ident(path, location, key), "path": location + "." + key,
                "action": action, "event": event, "status": status,
                "texts": local_text, "attributes": attrs,
                "style": obj.get("style", {}), "conditions": conditions,
                "element_type": obj.get("type"),
            })
    if not bindings:
        return None
    return {
        "id": ident("template", path), "kind": "template", "source": path,
        "title": pretty_name(path), "module": module_for(path),
        "bindings": bindings, "texts": text_values(data),
        "note": "连线终点为事件或运行时表达式，不代表已确认目标页面。",
    }


def qualified(name, package):
    if name.startswith("."):
        return package + name
    return name if "." in name else package + "." + name


def manifest_catalog(root):
    package = root.attrib.get("package", "")
    result = []
    for element in root.findall(".//activity") + root.findall(".//activity-alias"):
        name = element.attrib.get(ANDROID + "name", "")
        item = {
            "id": ident("activity", name), "name": qualified(name, package),
            "label": element.attrib.get(ANDROID + "label"),
            "module": module_for(name), "status": "declared_only",
            "exported": element.attrib.get(ANDROID + "exported", "unspecified"),
            "alias_target": element.attrib.get(ANDROID + "targetActivity"),
            "intent_filters": [],
        }
        for intent in element.findall("intent-filter"):
            item["intent_filters"].append({
                "actions": [x.attrib.get(ANDROID + "name") for x in intent.findall("action")],
                "categories": [x.attrib.get(ANDROID + "name") for x in intent.findall("category")],
                "data": [{k.removeprefix(ANDROID): v for k, v in x.attrib.items()} for x in intent.findall("data")],
            })
        result.append(item)
    return result


def xml_graph(path, root, strings=None):
    bindings = []
    for index, item in enumerate(root.iter()):
        handler = item.attrib.get(ANDROID + "onClick")
        if handler:
            text = item.attrib.get(ANDROID + "text", "")
            resolved_text = (strings or {}).get(text, text)
            bindings.append({
                "id": ident(path, index), "path": f"element[{index}]/@android:onClick",
                "action": handler, "event": handler, "status": "static_binding",
                "element_type": item.tag,
                "attributes": {k.removeprefix(ANDROID): v for k, v in item.attrib.items()},
                "texts": [{"value": resolved_text, "resource": text, "dynamic": resolved_text.startswith("@")}]
                if text else [],
                "style": {}, "conditions": [],
            })
    if not bindings:
        return None
    return {"id": ident("layout", path), "kind": "layout", "title": pretty_name(path),
            "module": module_for(path), "source": path, "bindings": bindings, "texts": []}


def navigation_method(reference):
    return ("Landroid/content/Intent;->" in reference and any(x in reference for x in ("<init>", "setClass", "setComponent"))) or any(
        x in reference for x in ("->startActivity(", "->startActivityForResult(", "SmartRouter;->buildRoute(",
                                "Lcom/alibaba/android/arouter/launcher/ARouter;->build(")
    )


def trace_navigation(instructions, owner, method, dex_name, package, block_starts=()):
    """Keep literals only inside a straight-line bytecode segment.

    Deliberately abandon values at control flow and unknown writes. A missing
    edge is preferable to connecting literals across different branches.
    """
    regs = {}
    pending = None
    output = []
    history = []
    joins = {off + operand[1] * 2 for off, name, operands, _ in instructions
             if name.startswith(("if-", "goto")) for operand in operands if int(operand[0]) == 3}
    joins.update(block_starts)
    for offset, name, operands, display in instructions:
        if offset in joins:
            regs.clear(); pending = None; history = []
        history.append(f"{offset:04x}: {name} {display}")
        history = history[-12:]
        register = [x[1] for x in operands if int(x[0]) == 0]
        resolved = [x[2] for x in operands if len(x) > 2 and int(x[0]) >= 0x100]
        reference = str(resolved[-1]) if resolved else ""
        if name.startswith(("if-", "goto", "packed-switch", "sparse-switch", "return", "throw")):
            regs.clear(); pending = None
        elif name.startswith("const-string") and register:
            regs[register[0]] = {"kind": "string", "value": reference}
        elif name == "const-class" and register:
            regs[register[0]] = {"kind": "class", "value": reference}
        elif name == "new-instance" and register:
            regs[register[0]] = {"kind": "object", "class": reference}
        elif name.startswith("move-result") and register:
            if pending is not None:
                regs[register[0]] = pending
            else:
                regs.pop(register[0], None)
            pending = None
        elif name.startswith("move-object") and len(register) >= 2:
            if register[1] in regs:
                regs[register[0]] = regs[register[1]]
            else:
                regs.pop(register[0], None)
        elif name.startswith("invoke"):
            pending = None
            values = [regs.get(r) for r in register]
            if reference.startswith("Landroid/content/Intent;->") and register:
                target = next((x["value"] for x in reversed(values) if x and x["kind"] == "class"), None)
                if "setClassName(" in reference:
                    literals = [x["value"] for x in values[1:] if x and x["kind"] == "string"]
                    if literals:
                        target = literals[-1]
                        if target.startswith("."):
                            target = literals[0] + target if len(literals) == 2 else None
                if any(part in reference for part in ("<init>", "setClass", "setComponent")):
                    obj = regs.get(register[0])
                    if obj:
                        obj.pop("target", None)
                if target and any(part in reference for part in ("<init>", "setClass(", "setClassName(")):
                    obj = regs.setdefault(register[0], {"kind": "object", "class": "Landroid/content/Intent;"})
                    obj["target"] = target
                    pending = obj
                elif "setComponent(" in reference and len(values) > 1 and values[1] and values[1].get("component_target"):
                    obj = regs.get(register[0])
                    if obj:
                        obj["target"] = values[1]["component_target"]
                        pending = obj
            if reference.startswith("Landroid/content/ComponentName;-><init>(") and values and values[0]:
                target = next((x["value"] for x in values[1:] if x and x["kind"] == "class"), None)
                if target:
                    values[0]["component_target"] = target
            if "SmartRouter;->buildRoute(" in reference or "Lcom/alibaba/android/arouter/launcher/ARouter;->build(" in reference:
                route = next((x["value"] for x in reversed(values) if x and x["kind"] == "string"), None)
                if route:
                    edge = {"kind": "route_construction", "target": route, "offset": offset,
                            "status": "static_binding", "snippet": list(history), "api": reference}
                    output.append(edge)
                    pending = {"kind": "route", "edge": edge}
            elif any(part in reference for part in ("Lcom/bytedance/router/SmartRoute;->", "Lcom/alibaba/android/arouter/facade/Postcard;->")) and values:
                obj = values[0]
                if obj and obj.get("kind") == "route":
                    if ";->open(" in reference or ";->navigation(" in reference:
                        obj["edge"].update(kind="route_launch", launch_offset=offset,
                                           launch_api=reference, launch_snippet=list(history))
                    elif reference.endswith(("Lcom/bytedance/router/SmartRoute;", "Lcom/alibaba/android/arouter/facade/Postcard;")):
                        pending = obj
            if "/router/mapping/" in owner and method.startswith("init(") and "Ljava/util/Map;->put(" in reference and len(values) == 3:
                key, value = values[1:]
                if key and value and key.get("kind") == value.get("kind") == "string" and re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[\w$]+)+", value["value"]):
                    output.append({"kind": "route_declaration", "route": key["value"], "target": value["value"],
                                   "offset": offset, "status": "declared_only", "snippet": list(history), "api": reference})
            if "->startActivity(" in reference or "->startActivityForResult(" in reference:
                intent = next((x for x in values if x and x.get("target")), None)
                if intent:
                    target = intent["target"]
                    if target.startswith("L") and target.endswith(";"):
                        target = target[1:-1].replace("/", ".")
                    output.append({"kind": "activity_launch", "target": target, "offset": offset,
                                   "status": "static_binding", "snippet": list(history), "api": reference})
        elif register and not name.startswith(("iput", "sput", "aput", "monitor", "check-cast", "nop")):
            regs.pop(register[0], None)
    for item in output:
        item.update(source_class=owner.removeprefix("L").removesuffix(";").replace("/", "."), method=method, dex=dex_name,
                    id=ident(dex_name, owner, method, item["offset"], item["target"]))
    return output


def scan_dex(data, name, event_names, output_dir, cache_key):
    from androguard.core.dex import DEX, determineException, determineNext
    dex = DEX(data)
    classes = list(dex.get_classes())
    method_ids = dex.get_methods()
    nav_indices = [index for index, method in enumerate(method_ids)
                   if navigation_method(method.get_class_name() + "->" + method.get_name() + method.get_descriptor())]
    pattern = re.compile(b"[\\x6e-\\x72\\x74-\\x78].(?:" + b"|".join(re.escape(struct.pack("<H", x)) for x in nav_indices) + b")", re.S) if nav_indices else None
    strings = dex.get_strings()
    event_ids = {i: value for i, value in enumerate(strings) if value in event_names}
    short_events = [i for i in event_ids if i <= 65535]
    event_pattern = re.compile(b"\\x1a.(?:" + b"|".join(re.escape(struct.pack("<H", i)) for i in short_events) + b")", re.S) if short_events else None
    jumbo_event_pattern = re.compile(b"\\x1b.(?:" + b"|".join(re.escape(struct.pack("<I", i)) for i in event_ids) + b")", re.S) if event_ids else None
    routes = []; references = []; catalog = []; methods_seen = 0; methods_decoded = 0
    for cls in classes:
        class_name = cls.get_name()
        catalog.append({"name": class_name.removeprefix("L").removesuffix(";").replace("/", "."), "super": cls.get_superclassname(), "dex": name})
        for method in cls.get_methods():
            methods_seen += 1
            code = method.get_code()
            if code is None:
                continue
            raw = code.get_bc().get_raw()
            has_nav = bool(pattern and pattern.search(raw)) or "/router/mapping/" in class_name
            has_event = bool((event_pattern and event_pattern.search(raw)) or (jumbo_event_pattern and jumbo_event_pattern.search(raw)))
            if not has_nav and not has_event:
                continue
            indexed = list(method.get_instructions_idx())
            instructions = [(off, ins.get_name(), ins.get_operands(), ins.get_output()) for off, ins in indexed]
            methods_decoded += 1
            method_name = method.get_name() + method.get_descriptor()
            if has_nav:
                starts = {target for off, ins in indexed for target in determineNext(ins, off, method) if target >= 0}
                starts.update(handler[1] for region in determineException(dex, method) for handler in region[2:])
                routes.extend(trace_navigation(instructions, class_name, method_name, name, "", starts))
            if has_event:
                for off, ins_name, operands, display in instructions:
                    if ins_name.startswith("const-string"):
                        for operand in operands:
                            if len(operand) > 2 and operand[2] in event_names:
                                references.append({"event": operand[2], "class_name": class_name.removeprefix("L").removesuffix(";").replace("/", "."),
                                                   "method": method_name, "dex": name, "offset": off})
    result = {"dex": name, "cache_key": cache_key, "classes": len(classes), "methods": methods_seen,
              "decoded_methods": methods_decoded, "routes": routes, "event_references": references,
              "class_catalog": catalog}
    (output_dir / (name + ".json")).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def scan_embedded(name, payload, report, depth=0):
    """Inspect compressed assets as data only; never execute bundled programs."""
    limit = 64 * 1024 * 1024
    if depth > 3:
        report["unparsed"].append({"path": name, "reason": "embedded_depth_limit"})
        return
    if name.endswith(".zst"):
        import zstandard
        try:
            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(payload)) as reader:
                expanded = reader.read(limit + 1)
            if len(expanded) > limit:
                raise ValueError("expanded asset exceeds 64 MiB safety limit")
            report["scan"]["zstd_expanded"] += 1
            return scan_embedded(name + "!expanded", expanded, report, depth + 1)
        except Exception as error:
            report["unparsed"].append({"path": name, "reason": "zstd: " + str(error)})
            return
    if payload.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as nested:
                infos = nested.infolist()
                if sum(i.file_size for i in infos) > limit or len(infos) > 10000:
                    raise ValueError("embedded archive exceeds inspection safety limit")
                report["scan"]["archives_expanded"] += 1
                for info in infos:
                    if info.is_dir():
                        continue
                    path = name + "!" + info.filename
                    report["asset_catalog"].append({"path": path, "size": info.file_size})
                    if info.filename.endswith((".json", ".js", ".zst", ".zip", ".abc", ".jar")):
                        scan_embedded(path, nested.read(info), report, depth + 1)
            return
        except Exception as error:
            report["unparsed"].append({"path": name, "reason": "archive: " + str(error)})
            return
    if name.endswith(".json") or payload.lstrip().startswith((b"{", b"[")):
        try:
            value = json.loads(payload)
            report["scan"]["embedded_json_parsed"] += 1
            graph = template_graph(name, value)
            if graph:
                report["graphs"].append(graph)
            return
        except (ValueError, UnicodeError):
            pass
    report["unparsed"].append({"path": name, "reason": "program_or_unrecognized_payload_not_decompiled",
                               "bytes": len(payload), "header_hex": payload[:16].hex()})


def extract(apk_path, destination, skip_dex=False, dex_limit=None):
    from androguard.core.axml import ARSCParser, AXMLPrinter
    from loguru import logger
    logger.remove()
    destination.mkdir(parents=True, exist_ok=True)
    cache = destination / "dex_evidence"; cache.mkdir(exist_ok=True)
    report = {"schema_version": 1, "source": "apk_static", "review_status": "pending_review",
              "generated_at": datetime.now(timezone.utc).isoformat(), "graphs": [], "activities": [],
              "routes": [], "event_references": [], "scan": {}, "unparsed": [], "asset_catalog": []}
    with apk_path.open("rb") as source:
        report["sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
    with zipfile.ZipFile(apk_path) as archive:
        names = archive.namelist()
        root = AXMLPrinter(archive.read("AndroidManifest.xml")).get_xml_obj()
        report["package"] = {"name": root.attrib.get("package"), "version_name": root.attrib.get(ANDROID + "versionName"),
                             "version_code": root.attrib.get(ANDROID + "versionCode")}
        report["activities"] = manifest_catalog(root)
        print("Reading resource table and XML layouts", flush=True)
        resources = ARSCParser(archive.read("resources.arsc"))
        string_table = resources.get_resolved_strings().get(root.attrib.get("package"), {})
        strings = {}
        for locale in ("DEFAULT", "zh-rCN", "zh"):
            for rid, value in string_table.get(locale, {}).items():
                if isinstance(value, str):
                    strings[f"@{rid:08X}"] = value
                    strings[f"@{rid:08x}"] = value
        for activity in report["activities"]:
            label = activity["label"]
            if label and label not in strings and re.fullmatch(r"@[0-9A-Fa-f]{8}", label):
                values = resources.get_resolved_res_configs(int(label[1:], 16))
                if values and isinstance(values[0][1], str):
                    strings[label] = values[0][1]
            if activity["label"] in strings:
                activity["resolved_label"] = strings[activity["label"]]
        report["resource_strings"] = [{"id": key, "value": value} for key, value in strings.items() if key == key.upper()]
        report["scan"] = {"apk_entries": len(names), "asset_json_total": 0, "asset_json_parsed": 0,
                          "xml_total": 0, "xml_parsed": 0, "script_total": 0,
                          "archives_expanded": 0, "zstd_expanded": 0, "embedded_json_parsed": 0,
                          "dex_total": len([n for n in names if re.fullmatch(r"classes\d*\.dex", n)]),
                          "dex_scanned": 0, "classes": 0, "methods": 0, "decoded_methods": 0}
        for name in names:
            if name.startswith("assets/"):
                report["asset_catalog"].append({"path": name, "size": archive.getinfo(name).file_size})
            if name.startswith("assets/") and name.endswith(".json"):
                report["scan"]["asset_json_total"] += 1
                try:
                    value = json.loads(archive.read(name))
                    report["scan"]["asset_json_parsed"] += 1
                    graph = template_graph(name, value)
                    if graph: report["graphs"].append(graph)
                except (ValueError, UnicodeError) as error:
                    report["unparsed"].append({"path": name, "reason": type(error).__name__})
            elif name.endswith(".xml") and not name.startswith(("assets/", "META-INF/")) and name != "AndroidManifest.xml":
                report["scan"]["xml_total"] += 1
                try:
                    xml = AXMLPrinter(archive.read(name)).get_xml_obj()
                    if xml is None: raise ValueError("no XML root")
                    report["scan"]["xml_parsed"] += 1
                    graph = xml_graph(name, xml, strings)
                    if graph: report["graphs"].append(graph)
                except Exception as error:
                    report["unparsed"].append({"path": name, "reason": type(error).__name__})
            elif name.startswith("assets/") and name.endswith((".js", ".zst", ".abc", ".zip", ".so", ".jar")):
                scan_embedded(name, archive.read(name), report)
                if name.endswith(".js"): report["scan"]["script_total"] += 1
        event_names = {binding["event"] for graph in report["graphs"] for binding in graph["bindings"] if binding["status"] == "static_binding"}
        cache_key = ident(CACHE_VERSION, report["sha256"], json.dumps(sorted(event_names)))
        dex_names = sorted([n for n in names if re.fullmatch(r"classes\d*\.dex", n)], key=lambda n: int(re.sub(r"\D", "", n) or "1"))
        if not skip_dex:
            for name in dex_names[:dex_limit]:
                cached = cache / (name + ".json")
                if cached.exists():
                    result = json.loads(cached.read_text(encoding="utf-8"))
                else:
                    result = None
                if not result or result.get("cache_key") != cache_key:
                    print(f"Scanning {name}", flush=True)
                    try:
                        result = scan_dex(archive.read(name), name, event_names, cache, cache_key)
                    except Exception as error:
                        report["unparsed"].append({"path": name, "reason": type(error).__name__ + ": " + str(error)})
                        print(f"Failed {name}: {error}", flush=True)
                        continue
                for key in ("classes", "methods", "decoded_methods"):
                    report["scan"][key] += result[key]
                report["scan"]["dex_scanned"] += 1
                report["routes"].extend(result["routes"])
                report["event_references"].extend(result["event_references"])
                gc.collect()
        report["scan"]["bindings"] = sum(len(g["bindings"]) for g in report["graphs"])
        report["scan"]["static_bindings"] = sum(b["status"] == "static_binding" for g in report["graphs"] for b in g["bindings"])
        report["scan"]["dynamic_bindings"] = report["scan"]["bindings"] - report["scan"]["static_bindings"]
        report["scan"]["graphs"] = len(report["graphs"])
        report["scan"]["activities"] = len(report["activities"])
        report["scan"]["route_fragments"] = len(report["routes"])
    report["modules"] = [{"id": key, "label": title} for key, title, _ in MODULES]
    report["limitations"] = [
        "仅分析所列版本APK，不是当前线上账号的真实界面。",
        "仅声明的Activity和功能目录不代表页面之间的可达路径。",
        "模板的静态事件绑定不等于目标页面已解析；运行时表达式保持未解析。",
        "原生跳转仅记录同一直线字节码段内可追踪的Intent目标或路由构造，条件、跨方法和动态分发未求解。",
        "资源位置是布局属性，不是当前设备上的可点击坐标。",
        "嵌入脚本、原生库、压缩动态包和服务器下发逻辑未据此还原完整业务流程。",
        "所有静态证据均待真机与人工审核，不自动进入Golden Flow。",
    ]
    (destination / "flow-evidence.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"package": report["package"], "scan": report["scan"]}, ensure_ascii=False), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--skip-dex", action="store_true")
    parser.add_argument("--dex-limit", type=int)
    args = parser.parse_args()
    extract(args.apk, args.output, args.skip_dex, args.dex_limit)
