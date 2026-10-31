#!/usr/bin/env python3
"""Serial local acquisition; upload only attributable, unreviewed evidence."""

import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import traceback

from extract_apk_flows import CACHE_VERSION, extract, ident
import mobile_package_lab as lab
from render_apk_flow_report import render


FILES = ("provenance.json", "flow-evidence.json", "interaction-map.json", "summary.json")


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def build_map(data, app):
    """Separate containment, declarations, event bindings and actual code calls."""
    nodes, edges, gaps = {}, [], []
    scope = app["key"] + ":" + data["package"]["version_name"] + ":"

    def node(kind, key, label, evidence):
        nid = scope + ident(kind, key)
        nodes.setdefault(nid, {"id": nid, "kind": kind, "label": label, "evidence": evidence})
        return nid

    def edge(kind, source, target, evidence):
        edges.append({"kind": kind, "from": source, "to": target, "evidence_id": evidence})

    for activity in data["activities"]:
        node("activity_declaration", activity["name"], activity.get("resolved_label") or activity["name"], activity["id"])
    for graph in data["graphs"]:
        component = node("component", graph["id"], graph["title"], graph["source"])
        for binding in graph["bindings"]:
            element = node("element", binding["id"], " / ".join(str(t["value"]) for t in binding["texts"] if not t.get("dynamic"))[:240] or binding["element_type"] or "unresolved label", binding["id"])
            event = node("event" if binding["status"] == "static_binding" else "runtime_expression", binding["id"], binding["event"], binding["id"])
            edge("contains_not_navigation", component, element, binding["id"])
            edge(binding["status"], element, event, binding["id"])
            gaps.append({"evidence_id": binding["id"], "reason": "event_destination_unresolved"})
    for route in data["routes"]:
        source = node("code_handler", route["source_class"] + route["method"], route["source_class"] + " :: " + route["method"], route["id"])
        if route["kind"] == "activity_launch":
            declared = any(a["name"] == route["target"] for a in data["activities"])
            target = node("activity_declaration" if declared else "code_target", route["target"], route["target"], route["id"])
        elif route["kind"] == "route_declaration":
            source = node("route", route["route"], route["route"], route["id"])
            target = node("registered_handler", route["target"], route["target"], route["id"])
        else:
            target = node("route", route["target"], route["target"], route["id"])
            gaps.append({"evidence_id": route["id"], "reason": "route_destination_and_runtime_conditions_need_review"})
        edge(route["kind"], source, target, route["id"])
    return {"schema_version": 1, "source": "apk_static", "review_status": "pending_review", "app": app,
            "package": data["package"], "sha256": data["sha256"], "nodes": list(nodes.values()), "edges": edges,
            "gaps": gaps, "limitations": data["limitations"]}


def validate(data, app, provenance, mapped):
    if data["package"]["name"] != app["android"]["package"] or data["sha256"] != provenance["sha256"]:
        raise ValueError("Package identity or SHA-256 mismatch")
    if not provenance["signature"]["verified"]:
        raise ValueError("Missing verified APK signature")
    if data["source"] != "apk_static" or data["review_status"] != "pending_review":
        raise ValueError("Static evidence promotion is forbidden")
    ids = [n["id"] for n in mapped["nodes"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate map node ids")
    ids = set(ids)
    if any(e["from"] not in ids or e["to"] not in ids for e in mapped["edges"]):
        raise ValueError("Dangling map edge")
    if sum(len(g["bindings"]) for g in data["graphs"]) != data["scan"]["bindings"]:
        raise ValueError("Binding count mismatch")


def upload(folder, server, remote):
    """Publish allowlisted JSON through a staging directory and compare every hash."""
    expected = {name: digest(folder / name) for name in FILES}
    write_json(folder / "checksums.json", expected)
    staging = remote + ".uploading"
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", server]
    subprocess.run(ssh + ["test ! -e " + shlex.quote(remote) + " && mkdir -p " + shlex.quote(staging)], check=True, timeout=45)
    subprocess.run(["scp", "-o", "BatchMode=yes", *[str(folder / f) for f in (*FILES, "checksums.json")], server + ":" + staging + "/"], check=True, timeout=240)
    code = ("import pathlib,json,hashlib; p=pathlib.Path(" + repr(staging) + "); "
            "expected=json.loads((p/'checksums.json').read_text()); "
            "actual={n:hashlib.sha256((p/n).read_bytes()).hexdigest() for n in expected}; "
            "assert actual==expected, 'remote checksum mismatch'; "
            "assert set(x.name for x in p.iterdir())==set(expected)|{'checksums.json'}; "
            "p.rename(" + repr(remote) + "); print(json.dumps(actual))")
    subprocess.run(ssh + ["python3 -c " + shlex.quote(code)], check=True, timeout=60)
    return expected


def batch_index(root, state):
    write_json(root / "batch-index.json", state)
    rows = []
    status_labels = {"verified_uploaded_input_deleted": "已校验入库", "failed_input_deleted": "未完成",
                     "started": "准备中", "downloading": "下载中", "extracting": "分析中", "uploaded": "已上传", "deferred_by_user": "按要求暂缓"}
    for item in state["apps"]:
        counts = item.get("counts", {})
        link = "<a href='" + html.escape(item["report"]) + "'>查看图册</a>" if item.get("report") else ""
        rows.append("<tr>" + "".join("<td>" + html.escape(str(value)) + "</td>" for value in (
            item["name"], status_labels.get(item["status"], item["status"]), item.get("version", "—"), counts.get("activities", "—"),
            counts.get("graphs", "—"), counts.get("bindings", "—"), counts.get("activity_launch", "—"),
            counts.get("route_launch", "—"), item.get("scan_coverage", "—"))) + "<td>" + link + "</td></tr>")
    document = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>14个App · 静态交互证据</title>
<style>body{font:15px 'PingFang SC','Microsoft YaHei',sans-serif;color:#26342e;background:#f7f9f7;margin:0}main{max-width:1440px;margin:48px auto;padding:0 32px}h1{font-size:30px}p{line-height:1.8;color:#5d6861}table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;padding:15px 12px;border-bottom:1px solid #e2e7e3}th{font-size:13px;color:#56635a}a{color:#287543}header{border-bottom:2px solid #287543;margin-bottom:26px}small{color:#68746c}</style>
<main><header><small>INTERMAP / APK STATIC / 2026-10-25</small><h1>常用App · 静态交互证据总览</h1>
<p>安装包反推结果，均未真机验证。页面声明、组件绑定与代码跳转分别计数，不能换算成完整业务流程或功能覆盖率。<br>顺丰、银行、运营商、公共服务和电力不在本批范围。抖音复用既有样本。</p></header>
<table><thead><tr><th>应用</th><th>状态</th><th>版本</th><th>页面声明</th><th>组件</th><th>绑定</th><th>页面调用</th><th>路由打开</th><th>DEX扫描</th><th>证据</th></tr></thead><tbody>""" + "".join(rows) + "</tbody></table></main></html>"
    (root / "index.html").write_text(document, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apps", nargs="+", default=["all"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dagre", required=True, type=Path)
    parser.add_argument("--server", default="root@loop-lulu.com")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.run_id):
        raise ValueError("Unsafe run id")
    config = lab.load_config(lab.DEFAULT_CONFIG)
    apps = lab.select_apps(config, args.apps)
    root = lab.DEFAULT_OUTPUT / "batches" / args.run_id
    root.mkdir(parents=True, exist_ok=True)
    index = root / "batch-index.json"
    state = json.loads(index.read_text()) if index.exists() else {
        "schema_version": 1, "source": "apk_static", "review_status": "pending_review", "run_id": args.run_id,
        "approved_app_keys": config["collection_approval"]["approved_app_keys"], "apps": []}
    for app in apps:
        previous = next((a for a in state["apps"] if a["key"] == app["key"]), None)
        if previous and previous["status"] == "verified_uploaded_input_deleted":
            continue
        if previous:
            state["apps"].remove(previous)
        item = {"key": app["key"], "name": app["name"], "status": "started"}
        state["apps"].append(item)
        batch_index(root, state)
        try:
            with tempfile.TemporaryDirectory(prefix="intermap-" + app["key"] + "-") as temp:
                if app["key"] == "douyin":
                    base = lab.DEFAULT_OUTPUT / "android/douyin/40.3.0"
                    data = json.loads((base / "flow-map-20261025/flow-evidence.json").read_text())
                    analysis = json.loads((base / "analysis-vendor.json").read_text())
                    provenance = {**analysis["provenance"], "sha256": data["sha256"], "signature": analysis["signature"],
                                  "reused_evidence": "android/douyin/40.3.0/flow-map-20261025", "extractor_version": 4}
                else:
                    print(app["key"] + ": fetching official metadata", flush=True)
                    if app["android"].get("vendor_download_url"):
                        metadata = {"source_type": "official_vendor_distribution", "source_name": app["name"] + " official site",
                                    "source_listing": app["android"]["vendor_source_page"], "fetched_at": lab.utc_now(),
                                    "package": app["android"]["package"], "download_url": app["android"]["vendor_download_url"],
                                    "source_config": app["android"].get("vendor_config_url"),
                                    "digest_note": "Vendor does not publish a digest here; package identity and APK signature must verify; SHA-256 retained."}
                    else:
                        metadata = lab.fetch_myapp_metadata(app)
                    item.update(status="downloading", version=metadata.get("version_name", "pending_package_inspection"), source=metadata)
                    batch_index(root, state)
                    apk = Path(temp) / "input.apk"
                    downloaded = lab.download_apk(metadata, apk)
                    badging = lab.parse_badging(lab.run_text([str(lab.find_tool("aapt2")), "dump", "badging", str(apk)]))
                    if badging["package"] != app["android"]["package"]:
                        raise ValueError("Downloaded package does not match approved app")
                    signature = lab.parse_signer_report(lab.run_text([str(lab.find_tool("apksigner")), "verify", "--verbose", "--print-certs", str(apk)]))
                    if not signature["verified"]:
                        raise ValueError("Signature verification failed")
                    provenance = {**metadata, **{k: downloaded[k] for k in ("size", "md5", "sha256", "resolved_url")},
                                  "signature": signature, "package_metadata": badging, "extractor_version": CACHE_VERSION}
                    item["status"] = "extracting"
                    batch_index(root, state)
                    data = extract(apk, Path(temp) / "extracted")
                data["app"] = {"key": app["key"], "name": app["name"]}
                data["extractor_version"] = provenance["extractor_version"]
                version = data["package"]["version_name"]
                if not re.fullmatch(r"[\w.+-]+", version):
                    raise ValueError("Unsafe package version")
                folder = root / "apps" / app["key"] / version
                folder.mkdir(parents=True, exist_ok=True)
                mapped = build_map(data, data["app"])
                validate(data, app, provenance, mapped)
                counts = dict(data["scan"])
                counts.update(Counter(r["kind"] for r in data["routes"]))
                summary = {"app": data["app"], "package": data["package"], "sha256": data["sha256"],
                           "source": "apk_static", "review_status": "pending_review", "counts": counts,
                           "nodes": len(mapped["nodes"]), "edges": len(mapped["edges"]), "gaps": len(mapped["gaps"]),
                           "complete_dex_scan": counts["dex_scanned"] == counts["dex_total"],
                           "not_a_complete_business_flow": True}
                for name, value in zip(FILES, (provenance, data, mapped, summary)):
                    write_json(folder / name, value)
                render(folder / "flow-evidence.json", args.dagre, folder / "index.html")
                remote = "/var/www/intermap-data/package_static/android/" + app["key"] + "/" + version + "/" + args.run_id
                upload(folder, args.server, remote)
                item.update(version=version, counts=counts, report=str((folder / "index.html").relative_to(root)),
                            server_path=remote, scan_coverage=f"{counts['dex_scanned']}/{counts['dex_total']}",
                            status="uploaded")
            item["status"] = "verified_uploaded_input_deleted"
            print(app["key"] + ": evidence verified, uploaded; temporary package and DEX cache deleted", flush=True)
        except Exception as error:
            item.update(status="failed_input_deleted", error=type(error).__name__ + ": " + str(error))
            traceback.print_exc()
        batch_index(root, state)
    print(json.dumps(state, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
