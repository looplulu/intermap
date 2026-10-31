#!/usr/bin/env python3
"""Build an offline, read-only report from unreviewed APK evidence."""

import argparse
import json
from pathlib import Path


def render(evidence, dagre, output, preview=None):
    data = json.loads(evidence.read_text(encoding="utf-8"))
    declarations = {}
    for edge in data["routes"]:
        if edge["kind"] == "route_declaration":
            declarations.setdefault(edge["route"], []).append(edge)
    for edge in data["routes"]:
        if edge["kind"] not in ("route_launch", "route_construction"):
            continue
        key = edge["target"].split("?", 1)[0]
        if key.startswith("aweme://"):
            key = "//" + key[len("aweme://"):]
        candidates = declarations.get(key, [])
        edge["resolved_targets"] = [{"name": item["target"], "evidence_id": item["id"]} for item in candidates]
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = Path(__file__).with_name("apk_flow_report.html").read_text(encoding="utf-8")
    html = template.replace("/*__DAGRE__*/", dagre.read_text(encoding="utf-8"))
    html = html.replace("/*__EVIDENCE__*/", serialized)
    output.write_text(html, encoding="utf-8")
    if preview:
        items = []
        for basename, title in [("to_all_tab", "订单：查看全部订单入口"), ("product_line", "订单：点击商品行"), ("per_order_refund", "售后：单笔订单售后信息")]:
            graph = next(g for g in data["graphs"] if g["source"] == f"assets/offline/ecommerce_order_list_component/{basename}/main.json")
            binding = graph["bindings"][0]
            items.append({"title": title, "source": graph["source"] + " · " + binding["path"], "nodes": [
                {"type": "包内组件 · 名称译注", "label": graph["title"]},
                {"type": "点击事件绑定", "label": binding["event"], "pending": binding["status"] == "runtime_value"},
                {"type": "断点 · 尚未还原", "label": "目标页面、显示条件及实际坐标，需要运行时证据", "pending": True},
            ]})
        for edge in data["routes"]:
            if edge["kind"] == "route_launch" and edge["source_class"].endswith(".SettingNewVersionActivity") and edge["resolved_targets"]:
                target = edge["resolved_targets"][0]["name"]
                label = {"ProfileEditActivity": "编辑个人资料", "SettingAccountAndSafetyActivity": "账号与安全", "PrivacyActivity": "隐私设置", "LocalLiveWallPaperActivity": "动态壁纸", "SystemPermissionActivity": "系统权限管理", "BusinessAccountProtocolActivity": "企业账号协议"}.get(target.split(".")[-1], edge["target"])
                items.append({"title": "设置页代码分支：" + label, "source": edge["dex"] + " · " + edge["source_class"] + " · " + edge["method"], "nodes": [
                    {"type": "源代码处理器 · 不代表已找到按钮", "label": "设置页处理代码（SettingNewVersionActivity）"},
                    {"type": "代码中调用路由打开 · 名称译注", "label": label + "：" + edge["target"]},
                    {"type": "路由表绑定的处理器 · 未真机验证", "label": target},
                ]})
        preview_template = Path(__file__).with_name("apk_flow_preview.html").read_text(encoding="utf-8")
        preview.write_text(preview_template.replace("/*__ITEMS__*/", json.dumps(items, ensure_ascii=False).replace("<", "\\u003c")), encoding="utf-8")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("dagre", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    render(args.evidence, args.dagre, args.output, args.preview)
